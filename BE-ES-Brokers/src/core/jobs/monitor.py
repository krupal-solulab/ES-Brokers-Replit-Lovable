"""Scheduled-monitor infrastructure.

A ``ScheduledMonitor`` is a named, cadence-driven callable that inspects persisted
engine output and emits ``MonitorAlertIn`` records.  The arq cron job
``run_scheduled_monitors`` iterates every registered monitor across every tenant,
persisting alerts with deduplication so the cron can fire frequently without spam.

KB06 in force: a monitor's ``run`` MUST only re-invoke existing deterministic engine
logic or read already-persisted engine output — it MUST NOT compute, alter, or
fabricate a number itself.

Usage (in any workflow module):
    from core.jobs.monitor import MonitorAlertIn, register_monitor, ScheduledMonitor

    class _MyMonitor:
        name = "my_monitor"
        workflow = "binder_issuance"

        async def run(self, session, ctx, as_of):
            # ... re-run or read existing engine output ...
            return [MonitorAlertIn(entity_ref="bind_123", alert_type="BIND_STALE",
                                   severity="WARN", payload={"days": 5})]

    register_monitor(_MyMonitor())
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.common.dtos import Ctx
from core.common.enums import Role
from core.db import async_session_factory
from core.models import MonitorAlert as MonitorAlertRow
from core.models import Tenant

_log = logging.getLogger(__name__)

# ── Alert severity ────────────────────────────────────────────────────────────

SEVERITY_INFO = "INFO"
SEVERITY_WARN = "WARN"
SEVERITY_URGENT = "URGENT"


# ── Monitor output DTO ────────────────────────────────────────────────────────

class MonitorAlertIn(BaseModel):
    """What a monitor's ``run`` method returns per detected condition.

    ``payload`` MUST be the triggering engine output verbatim — never a
    re-derived or fabricated number (KB06).
    """

    entity_ref: str
    alert_type: str
    severity: str  # SEVERITY_INFO | SEVERITY_WARN | SEVERITY_URGENT
    payload: dict[str, Any] = {}


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class ScheduledMonitor(Protocol):
    """Contract every monitor must satisfy."""

    #: Unique identifier — used for MONITOR_CRON_<NAME> env override lookup.
    name: str
    #: Workflow module the alerts belong to (e.g. ``"binder_issuance"``).
    workflow: str

    async def run(
        self,
        session: AsyncSession,
        ctx: Ctx,
        as_of: date,
    ) -> list[MonitorAlertIn]:
        """Return alerts for one tenant as of ``as_of``.

        MUST be idempotent per (entity_ref, alert_type, as_of): the caller
        handles deduplication at the DB level, but the monitor should not
        rely on that as a substitute for idempotent logic.
        An empty list is a valid, successful run — not an error.
        """
        ...


# ── Registry ──────────────────────────────────────────────────────────────────

_registry: dict[str, ScheduledMonitor] = {}


def register_monitor(monitor: ScheduledMonitor) -> None:
    """Register a monitor.  Call once at module import time (top of workflow package)."""
    if monitor.name in _registry:
        _log.warning("monitor %r already registered — replacing", monitor.name)
    _registry[monitor.name] = monitor
    _log.debug("registered monitor %r (workflow=%s)", monitor.name, monitor.workflow)


def get_monitors() -> list[ScheduledMonitor]:
    """Return all registered monitors in registration order."""
    return list(_registry.values())


def get_monitor(name: str) -> ScheduledMonitor | None:
    """Return a single registered monitor by name, or None if unknown."""
    return _registry.get(name)


# ── Cron expression helper ────────────────────────────────────────────────────

def _cron_to_arq_kwargs(expr: str) -> dict[str, Any]:
    """Translate a minimal cron expression to kwargs for ``arq.cron()``.

    Supported syntax: ``"minute hour * * *"``
    Fields beyond hour are ignored (always run every day/month/weekday).
    Each field supports: ``*`` (any), a fixed integer, or ``*/N`` (every N).
    Comma-separated lists (``"0,30"``) are also supported for minute/hour.

    Returns an empty dict (runs at every minute) on parse failure — the caller
    logs a warning and the cron still fires, just more often than intended.
    """
    try:
        parts = expr.strip().split()
        minute_str = parts[0] if len(parts) > 0 else "*"
        hour_str = parts[1] if len(parts) > 1 else "*"

        def _expand(s: str, max_val: int) -> set[int] | None:
            if s == "*":
                return None
            if "," in s:
                return {int(v.strip()) for v in s.split(",")}
            if s.startswith("*/"):
                step = int(s[2:])
                return {i for i in range(0, max_val + 1, step)}
            return {int(s)}

        kwargs: dict[str, Any] = {}
        m = _expand(minute_str, 59)
        h = _expand(hour_str, 23)
        if m is not None:
            kwargs["minute"] = m
        if h is not None:
            kwargs["hour"] = h
        return kwargs
    except Exception as exc:
        _log.warning("could not parse cron expression %r: %s — defaulting to every minute", expr, exc)
        return {}


def get_monitor_cadence(monitor_name: str, default_expr: str) -> str:
    """Return the cron expression for *monitor_name*.

    Checks ``MONITOR_CRON_<NAME>`` (uppercased) first; falls back to
    ``default_expr`` (which is itself ``MONITOR_CRON_DEFAULT`` or the config
    default).
    """
    env_key = f"MONITOR_CRON_{monitor_name.upper()}"
    return os.environ.get(env_key, default_expr)


# ── Arq task ──────────────────────────────────────────────────────────────────

async def run_scheduled_monitors(
    arq_ctx: dict[str, Any],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Arq task: run every registered monitor across every tenant.

    - ``as_of`` defaults to ``date.today()`` when called by the cron; pass a
      fixed date in tests for deterministic fixture-based runs (mirrors the
      ``as_of`` override pattern in binder_issuance/router.py).
    - One failing monitor NEVER blocks siblings — each monitor×tenant pair
      runs in its own isolated session; failures are logged and counted.
    - Empty result sets are valid, logged as zero alerts, not an error.
    """
    run_date = as_of if as_of is not None else date.today()
    monitors = get_monitors()

    summary: dict[str, Any] = {
        "as_of": run_date.isoformat(),
        "monitors_run": 0,
        "alerts_created": 0,
        "errors": [],
    }

    if not monitors:
        _log.info("run_scheduled_monitors: no monitors registered — nothing to do")
        return summary

    # Fetch all tenants once in a short-lived session.
    async with async_session_factory() as session:
        tenants: list[Tenant] = list(
            (await session.execute(select(Tenant))).scalars().all()
        )

    if not tenants:
        _log.info("run_scheduled_monitors: no tenants found")
        return summary

    for tenant in tenants:
        ctx = Ctx(
            tenant_id=tenant.id,
            vertical=tenant.vertical,
            user_id="system",
            role=Role.ADMIN,
        )

        for monitor in monitors:
            try:
                async with async_session_factory() as session:
                    alert_ins = await monitor.run(session, ctx, run_date)

                    created = 0
                    for alert_in in alert_ins:
                        dedupe_key = (
                            f"{tenant.id}:{alert_in.alert_type}"
                            f":{alert_in.entity_ref}:{run_date.isoformat()}"
                        )
                        existing = (
                            await session.execute(
                                select(MonitorAlertRow).where(
                                    col(MonitorAlertRow.dedupe_key) == dedupe_key
                                )
                            )
                        ).scalar_one_or_none()

                        if existing is None:
                            session.add(
                                MonitorAlertRow(
                                    tenant_id=tenant.id,
                                    vertical=tenant.vertical,
                                    workflow=monitor.workflow,
                                    entity_ref=alert_in.entity_ref,
                                    alert_type=alert_in.alert_type,
                                    severity=alert_in.severity,
                                    dedupe_key=dedupe_key,
                                    payload=alert_in.payload,
                                )
                            )
                            created += 1

                    await session.commit()
                    summary["alerts_created"] += created
                    summary["monitors_run"] += 1
                    _log.info(
                        "monitor %r / tenant %r: %d alert(s) created (as_of=%s)",
                        monitor.name, tenant.id, created, run_date,
                    )

            except Exception as exc:
                err = f"{monitor.name}/{tenant.id}: {exc}"
                summary["errors"].append(err)
                _log.exception("monitor %r failed for tenant %r: %s", monitor.name, tenant.id, exc)

                # Write an error record via the existing job-run error path.
                try:
                    from core.jobs.service import JobRunService, JobStatus  # local import avoids circular

                    async with async_session_factory() as err_session:
                        run_id = await JobRunService.create(
                            err_session,
                            job_name=f"monitor:{monitor.name}",
                            tenant_id=tenant.id,
                            args={"as_of": run_date.isoformat()},
                        )
                        await JobRunService.mark(err_session, run_id, JobStatus.ERROR, error=str(exc))
                except Exception as inner:
                    _log.error("could not write job-error record: %s", inner)

    return summary
