"""Scheduled monitor for the Quote Comparison workflow — G4.

One monitor registered here:
  quote_validity_window   QC-07 / FR-14 / FR-15 / FR-16 / FR-26

KB06 in force: ALL urgency computation is delegated to
``comparison_engine.recompute_urgency_from_payload`` — the same projection
already called on every GET request.  No business-day calendar logic lives
here; the engine's ``_validity_days_remaining`` (calendar days) is reused
verbatim.  The monitor's job is to iterate stored payloads, call the engine,
and persist the results as MonitorAlerts.

Alert types
-----------
QUOTE_VALIDITY_URGENT  — remaining validity window below threshold AND
                         no broker action logged (FR-15).  Also fires for
                         unresolved dependency subjectivities (FR-16) and
                         material subjectivities — these all appear as
                         separate urgency flags from the engine.
QUOTE_LAPSED           — status is LAPSED; emitted ONCE (cross-day
                         deduplication via pre-existing alert check).

Broker-action guard
-------------------
"No broker action logged" = status is PENDING_REVIEW.
PRESENTED (quote selected) and REVISION_REQUESTED (revision logged) both
indicate a broker acted; those items are skipped for QUOTE_VALIDITY_URGENT.
LAPSED items receive a one-off INFO alert regardless of broker action.

Single-quote coverage
---------------------
``recompute_urgency_from_payload`` handles single-quote payloads natively
(FR-14) — no special-case branching needed here.

Threshold override
------------------
``get_effective_setting(tenant_id, "quote_validity_urgency_threshold_days",
DEFAULT)`` is used so the Admin Panel's per-tenant override system is
respected without adding a second config source.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.admin.settings_override import get_effective_setting
from core.common.dtos import Ctx
from core.jobs.monitor import (
    SEVERITY_INFO,
    SEVERITY_URGENT,
    MonitorAlertIn,
    register_monitor,
)
from core.models import MonitorAlert as MonitorAlertRow
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from verticals.es.workflows.quote_comparison.comparison_engine import (
    VALIDITY_URGENCY_THRESHOLD_DAYS,
    recompute_urgency_from_payload,
)

_log = logging.getLogger(__name__)

_WORKFLOW = "quote_comparison"
_THRESHOLD_SETTING_KEY = "quote_validity_urgency_threshold_days"

# Statuses that indicate a broker has already acted — suppress QUOTE_VALIDITY_URGENT.
_BROKER_ACTED_STATUSES = {"PRESENTED", "REVISION_REQUESTED", "LAPSED"}


# ── Helper ─────────────────────────────────────────────────────────────────────

async def _lapsed_alert_exists(
    session: AsyncSession,
    tenant_id: str,
    item_id: str,
) -> bool:
    """Return True if any QUOTE_LAPSED MonitorAlert already exists for this item
    (from ANY prior run, not just today's).  Used to enforce "emit once" semantics
    for lapsed quotes — the infrastructure deduplicates within a day via as_of_day
    in the dedupe_key, but we need cross-day uniqueness for LAPSED."""
    row = (
        await session.execute(
            select(MonitorAlertRow).where(
                col(MonitorAlertRow.tenant_id) == tenant_id,
                col(MonitorAlertRow.alert_type) == "QUOTE_LAPSED",
                col(MonitorAlertRow.entity_ref) == item_id,
            )
        )
    ).first()
    return row is not None


async def _iter_quote_payloads(
    session: AsyncSession, tenant_id: str
) -> list[tuple[str, dict[str, Any]]]:
    """Return (item_id, payload_dict) pairs for all quote_comparison review items
    that have an attached OutputPackage, for this tenant."""
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

    results: list[tuple[str, dict[str, Any]]] = []
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
        results.append((item.id, raw))
    return results


# ── Monitor ────────────────────────────────────────────────────────────────────

class _QuoteValidityWindowMonitor:
    """QC-07 / FR-14 / FR-15 / FR-16 / FR-26 — persistent validity-window check.

    Iterates all quote_comparison items for the tenant and calls
    ``recompute_urgency_from_payload`` (the engine's own projection, KB06) to
    determine which items need alerting.  Persists results as MonitorAlerts so
    the queue can surface urgency proactively without waiting for a GET request.
    """

    name = "quote_validity_window"
    workflow = _WORKFLOW

    async def run(
        self,
        session: AsyncSession,
        ctx: Ctx,
        as_of: date,
    ) -> list[MonitorAlertIn]:
        alerts: list[MonitorAlertIn] = []

        # Per-tenant threshold override (admin settings system).
        threshold = int(
            get_effective_setting(
                ctx.tenant_id,
                _THRESHOLD_SETTING_KEY,
                VALIDITY_URGENCY_THRESHOLD_DAYS,
            )
        )

        pairs = await _iter_quote_payloads(session, ctx.tenant_id)

        for item_id, payload in pairs:
            status: str = payload.get("status", "PENDING_REVIEW")
            submission_id: str = payload.get("submission_id") or item_id
            named_insured: str | None = payload.get("named_insured")

            # ── LAPSED: emit once, then never again ─────────────────────────
            if status == "LAPSED":
                already_alerted = await _lapsed_alert_exists(session, ctx.tenant_id, item_id)
                if not already_alerted:
                    alerts.append(
                        MonitorAlertIn(
                            entity_ref=item_id,
                            alert_type="QUOTE_LAPSED",
                            severity=SEVERITY_INFO,
                            payload={
                                "submission_id": submission_id,
                                "named_insured": named_insured,
                            },
                        )
                    )
                continue  # nothing else to check for a lapsed item

            # ── Broker action logged — skip urgency check ────────────────────
            if status in _BROKER_ACTED_STATUSES:
                continue

            # ── PENDING_REVIEW: recompute urgency (KB06) ─────────────────────
            # ``recompute_urgency_from_payload`` handles single-quote payloads
            # natively (FR-14); no special-case branching needed.
            try:
                updated = recompute_urgency_from_payload(payload, as_of, threshold)
            except Exception as exc:
                _log.warning(
                    "recompute_urgency_from_payload failed for item=%s: %s", item_id, exc
                )
                continue

            urgency_flags: list[dict[str, Any]] = updated.get("urgency_flags") or []

            for flag in urgency_flags:
                quote_id: str = flag.get("quote_id") or ""
                flag_type: str = flag.get("flag_type") or "validity_window"
                detail: str = flag.get("detail") or ""

                # entity_ref per (item, quote) so each alert is independently
                # deduped and can be individually dismissed.
                alerts.append(
                    MonitorAlertIn(
                        entity_ref=f"{item_id}:{quote_id}",
                        alert_type="QUOTE_VALIDITY_URGENT",
                        severity=SEVERITY_URGENT,
                        payload={
                            # Verbatim engine output fields — KB06.
                            "submission_id": submission_id,
                            "quote_id": quote_id,
                            "flag_type": flag_type,
                            "detail": detail,
                            "named_insured": named_insured,
                            "threshold_days": threshold,
                        },
                    )
                )

        return alerts


# ── Registration ───────────────────────────────────────────────────────────────

register_monitor(_QuoteValidityWindowMonitor())

_log.debug("quote_validity_window monitor registered")
