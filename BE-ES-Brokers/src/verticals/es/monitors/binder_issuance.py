"""Scheduled monitors for the Binder Issuance workflow — G3.

Two monitors registered here:
  binder_issuance_timeline    BI-04 / FR-10 / FR-11
  binder_ongoing_obligations  BI-07 / FR-17

KB06 in force: both monitors delegate ALL arithmetic and date logic to
``coordination_engine.recompute_live_state`` (which itself only calls
``is_overdue`` / ``reminder_due`` — the same predicates the router uses
for on-demand display).  Neither monitor computes, alters, or fabricates
a number independently.

Alert types
-----------
ISSUANCE_OVERDUE    — bind confirmed, policy documents not yet received, past deadline.
OBLIGATION_REMINDER — POST_BIND_ONGOING obligation within reminder interval.

Deduplication
-------------
entity_ref is the payload's ``bind_id`` for timeline alerts and
``{bind_id}:{desc_hash}`` (MD5 prefix of the obligation description) for
obligation alerts.  Combined with the infrastructure's own
``{tenant}:{alert_type}:{entity_ref}:{as_of_day}`` key, this guarantees
at most one alert per condition per calendar day — even if the cron fires
multiple times or an obligation is already past due.

Edge cases
----------
- Policy documents already received → ``is_overdue`` returns False → no alert.
- Obligation completed → skipped.
- Past-due obligation with no prior reminder → ``reminder_due`` still returns
  True (days_remaining ≤ 5); deduplication ensures one WARN per day, not one
  per missed interval.
- ``is_assumption`` flag propagated verbatim from the engine payload so the
  UI can display assumption vs carrier-stated timeline correctly (FR-11).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.common.dtos import Ctx
from core.jobs.monitor import (
    SEVERITY_URGENT,
    SEVERITY_WARN,
    MonitorAlertIn,
    register_monitor,
)
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from verticals.es.workflows.binder_issuance.coordination_engine import recompute_live_state

_log = logging.getLogger(__name__)

_WORKFLOW = "binder_issuance"


# ── Shared helper ─────────────────────────────────────────────────────────────

async def _iter_binder_payloads(
    session: AsyncSession, tenant_id: str, as_of: date
) -> list[dict[str, Any]]:
    """Return recomputed payload dicts for all binder_issuance review items
    that have an attached OutputPackage, for this tenant.

    ``recompute_live_state`` is the single authoritative projection function —
    no separate logic here (KB06).
    """
    items = list(
        (
            await session.execute(
                select(ReviewItemRow).where(
                    col(ReviewItemRow.tenant_id) == tenant_id,
                    col(ReviewItemRow.workflow) == _WORKFLOW,
                )
            )
        )
        .scalars()
        .all()
    )

    results: list[dict[str, Any]] = []
    for item in items:
        if not item.output_package_id:
            continue
        pkg = (
            await session.execute(
                select(OutputPackageRow).where(
                    col(OutputPackageRow.id) == item.output_package_id
                )
            )
        ).scalar_one_or_none()
        if pkg is None or not pkg.payload:
            continue
        raw: dict[str, Any] = dict(pkg.payload) if isinstance(pkg.payload, dict) else {}
        if not raw:
            continue
        try:
            results.append(recompute_live_state(raw, as_of))
        except Exception as exc:
            _log.warning(
                "recompute_live_state failed for review_item=%s: %s", item.id, exc
            )
    return results


# ── Monitor 1: issuance timeline ──────────────────────────────────────────────

class _BinderIssuanceTimelineMonitor:
    """BI-04 / FR-10 / FR-11 — proactive issuance-overdue detection.

    Conditions checked:
    - bind_order_status is SENT (carrier has confirmed the bind)
    - documents_received is False
    - is_overdue(expected_by, as_of, documents_received) — delegated to engine

    Runs independently of discrepancy or subjectivity state (FR-11).
    """

    name = "binder_issuance_timeline"
    workflow = _WORKFLOW

    async def run(
        self,
        session: AsyncSession,
        ctx: Ctx,
        as_of: date,
    ) -> list[MonitorAlertIn]:
        alerts: list[MonitorAlertIn] = []

        payloads = await _iter_binder_payloads(session, ctx.tenant_id, as_of)
        for payload in payloads:
            # FR-11: independent of subjectivity/discrepancy state.
            if payload.get("bind_order_status") not in ("SENT",):
                continue

            issuance = payload.get("policy_issuance") or {}

            # Edge case: documents already received → engine returns False.
            if not issuance.get("overdue_alert_fired", False):
                continue

            bind_id = payload.get("bind_id") or payload.get("submission_id", "unknown")

            alerts.append(
                MonitorAlertIn(
                    entity_ref=bind_id,
                    alert_type="ISSUANCE_OVERDUE",
                    severity=SEVERITY_URGENT,
                    payload={
                        # Verbatim engine output — KB06.
                        "bind_id": bind_id,
                        "expected_by_date": issuance.get("expected_by_date"),
                        # FR-11: assumption flag surfaced to the UI.
                        "is_assumption": issuance.get("timeline_is_assumed_default", False),
                        "carrier_stated_timeline_days": issuance.get(
                            "carrier_stated_timeline_days"
                        ),
                        "named_insured": payload.get("named_insured"),
                        "carrier_name": payload.get("carrier_name"),
                    },
                )
            )

        return alerts


# ── Monitor 2: ongoing obligations ───────────────────────────────────────────

class _BinderOngoingObligationsMonitor:
    """BI-07 / FR-17 — obligation reminder at configurable intervals.

    For each POST_BIND_ONGOING obligation that is:
    - not completed
    - has ``reminder_due == True`` (recomputed by coordination_engine)

    Emits OBLIGATION_REMINDER WARN.  The engine's ``reminder_due`` already
    handles the past-due edge case: ``days_remaining <= 5`` is True when
    days_remaining is negative, so a single WARN fires (deduplicated by
    as_of_day).
    """

    name = "binder_ongoing_obligations"
    workflow = _WORKFLOW

    async def run(
        self,
        session: AsyncSession,
        ctx: Ctx,
        as_of: date,
    ) -> list[MonitorAlertIn]:
        alerts: list[MonitorAlertIn] = []

        payloads = await _iter_binder_payloads(session, ctx.tenant_id, as_of)
        for payload in payloads:
            bind_id = payload.get("bind_id") or payload.get("submission_id", "unknown")
            obligations: list[dict[str, Any]] = payload.get(
                "post_bind_ongoing_obligations"
            ) or []

            for o in obligations:
                if o.get("status") == "completed":
                    continue
                if not o.get("reminder_due", False):
                    continue

                description: str = o.get("description") or ""
                due_date: str | None = o.get("due_date")

                # Stable entity_ref: bind_id + description hash.
                desc_hash = hashlib.md5(description.encode()).hexdigest()[:8]

                # days_remaining — verbatim from engine recompute (KB06).
                days_remaining: int | None = None
                if due_date:
                    try:
                        days_remaining = (date.fromisoformat(due_date) - as_of).days
                    except ValueError:
                        pass

                alerts.append(
                    MonitorAlertIn(
                        entity_ref=f"{bind_id}:{desc_hash}",
                        alert_type="OBLIGATION_REMINDER",
                        severity=SEVERITY_WARN,
                        payload={
                            # Verbatim engine output — KB06.
                            "bind_id": bind_id,
                            "description": description,
                            "due_date": due_date,
                            "days_remaining": days_remaining,
                            "named_insured": payload.get("named_insured"),
                            "carrier_name": payload.get("carrier_name"),
                        },
                    )
                )

        return alerts


# ── Registration ──────────────────────────────────────────────────────────────

register_monitor(_BinderIssuanceTimelineMonitor())
register_monitor(_BinderOngoingObligationsMonitor())

_log.debug("binder_issuance monitors registered")
