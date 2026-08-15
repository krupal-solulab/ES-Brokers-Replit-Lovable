"""Scheduled monitor for Carrier Appetite Intelligence — G6.

One monitor registered here:
  carrier_appetite_batch   FR-1 / FR-4 / FR-5 / FR-6 / CI-01..CI-05

KB06 in force: ALL consistency scoring delegates verbatim to
``score_pattern()`` and ``compute_metadata_refresh()`` in consistency_engine.py.
The monitor adds only scheduling + the two narrow write-backs CI-03/CI-04 require.

Per-run behavior (one pass per tenant, all carriers with live signals)
----------------------------------------------------------------------
1. Discover carriers with real declination signals via ``discover_live_carriers()``.
2. For each carrier, run ``CarrierAppetiteIntelligencePipeline.run_live()`` —
   the identical entry point used by the router's ``/run-live`` endpoint.
3. Dispatch on ``pattern_type``:

   CONFIRMED_CONSISTENT (CI-03)
     → Call ``CarrierProfileService.refresh_metadata()`` with a typed
       ``MetadataRefreshDTO`` constructed from ``compute_metadata_refresh()``'s
       output — the strict two-field gate enforced at the type level (FR-4).
     → Emit CI_METADATA_REFRESHED INFO MonitorAlert.
     → Idempotent: skip if the current profile version was already refreshed
       today by CI (source == CI_METADATA_REFRESH AND created_at.date() == as_of).

   GENUINE_INCONSISTENCY (CI-04)
     → Enqueue the OutputPackage as a ReviewItem (PENDING_REVIEW) via
       ``DefaultReviewQueueService``.  The existing approve/dismiss endpoints in
       carrier_profiles/router.py discover it by suggestion_id + carrier_id in
       the stored payload — no new endpoints needed (FR-5 / FR-6).
     → Emit CI_SUGGESTION_CREATED WARN MonitorAlert.
     → Idempotent: skip if a PENDING_REVIEW CAI ReviewItem already exists for
       this carrier_id to prevent duplicate inbox entries.

   INSUFFICIENT_SIGNAL (CI-05 / the default)
     → Produce nothing (correct, low suggestion volume is expected per spec).

Edge-case notes
---------------
- Account-specific decline ZERO contribution: already enforced in
  ``classify_reason_scope()`` / ``score_pattern()`` — KB06, no duplication here.
- Concurrent human edit vs metadata refresh: both preserved as separate
  version rows by the append-only store — no conflict detection needed.
- No new signal collection: ``discover_live_carriers()`` reads only
  already-logged Quote Comparison OutputPackage rows (CI-01).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.common.dtos import Ctx
from core.jobs.monitor import (
    SEVERITY_INFO,
    SEVERITY_WARN,
    MonitorAlertIn,
    register_monitor,
)
from core.llm import build_llm_service
from core.models import CarrierAppetiteProfile as ProfileRow
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.review_queue import DefaultReviewQueueService
from verticals.es.carrier_profile_store import (
    CarrierProfileService,
    MetadataRefreshDTO,
    SOURCE_CI,
)
from verticals.es.workflows.carrier_appetite_intelligence.consistency_engine import (
    compute_metadata_refresh,
)
from verticals.es.workflows.carrier_appetite_intelligence.live_signal_builder import (
    discover_live_carriers,
)
from verticals.es.workflows.carrier_appetite_intelligence.service import (
    WORKFLOW_NAME,
    CarrierAppetiteIntelligencePipeline,
)

_log = logging.getLogger(__name__)


# ── Idempotency helpers ────────────────────────────────────────────────────────

async def _already_refreshed_today(
    session: AsyncSession, tenant_id: str, carrier_id: str, as_of: date
) -> bool:
    """True if the current profile version was already written by CI today.

    Prevents duplicate metadata refreshes when the scheduler fires more than
    once per day (e.g. replays) or the monitor is run on-demand alongside the
    scheduler cadence.
    """
    row = (
        await session.execute(
            select(ProfileRow)
            .where(
                col(ProfileRow.tenant_id) == tenant_id,
                col(ProfileRow.carrier_id) == carrier_id,
                col(ProfileRow.source) == SOURCE_CI,
            )
            .order_by(col(ProfileRow.created_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    created_date = (
        row.created_at.date()
        if isinstance(row.created_at, datetime)
        else row.created_at
    )
    return created_date == as_of


async def _pending_suggestion_exists(
    session: AsyncSession, tenant_id: str, carrier_id: str
) -> bool:
    """True if a PENDING_REVIEW ReviewItem for this carrier_id already exists.

    Prevents duplicate suggestion-inbox entries across scheduled runs.  A
    suggestion should remain PENDING until a human acts on it — the monitor must
    not stack duplicates behind it.
    """
    items = (
        await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.tenant_id) == tenant_id,
                col(ReviewItemRow.workflow) == WORKFLOW_NAME,
                col(ReviewItemRow.status) == "PENDING_REVIEW",
            )
        )
    ).scalars().all()

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
        if pkg.payload.get("carrier_id") == carrier_id:
            return True
    return False


# ── Monitor ────────────────────────────────────────────────────────────────────

class _CarrierAppetiteBatchMonitor:
    """FR-1 / CI-01..CI-05 scheduled batch — runs the CI aggregation +
    consistency engine per carrier on a periodic cadence.

    The expected dominant outcome for any run is suppression (CI-05): most
    carrier/class combos will have INSUFFICIENT_SIGNAL most of the time.  A
    low suggestion volume is correct, not a bug.
    """

    name = "carrier_appetite_batch"
    workflow = WORKFLOW_NAME

    async def run(
        self,
        session: AsyncSession,
        ctx: Ctx,
        as_of: date,
    ) -> list[MonitorAlertIn]:
        alerts: list[MonitorAlertIn] = []

        # Discover all carriers with at least one classifiable live signal
        # (CI-01 — reads already-logged QC OutputPackage rows, no new collection).
        carriers = await discover_live_carriers(session, ctx)
        if not carriers:
            _log.debug(
                "carrier_appetite_batch: no live carriers with signals for tenant=%s",
                ctx.tenant_id,
            )
            return alerts

        review_queue = DefaultReviewQueueService()

        for carrier in carriers:
            carrier_id: str = carrier["carrier_id"]
            carrier_name: str = carrier["carrier_name"]

            try:
                pipeline = CarrierAppetiteIntelligencePipeline(llm=build_llm_service())
                output = await pipeline.run_live(ctx, session, carrier_name)
            except Exception as exc:
                _log.warning(
                    "carrier_appetite_batch: pipeline.run_live failed for carrier=%r: %s",
                    carrier_name,
                    exc,
                )
                continue

            payload: dict[str, Any] = output.payload or {}
            pattern_type: str = payload.get("pattern_type", "INSUFFICIENT_SIGNAL")

            # ── CONFIRMED_CONSISTENT (CI-03) ──────────────────────────────────
            if pattern_type == "CONFIRMED_CONSISTENT":
                if await _already_refreshed_today(session, ctx.tenant_id, carrier_id, as_of):
                    _log.debug(
                        "carrier_appetite_batch: skipping duplicate CI refresh for carrier=%r",
                        carrier_id,
                    )
                    continue

                current_confidence: str = payload.get("metadata_refresh", {}).get(
                    "appetite_confidence",
                ) or "medium"
                refresh_fields = compute_metadata_refresh(
                    current_confidence,  # engine already computed new tier; use as starting point
                    as_of,
                )
                # Use the engine's own output — KB06.  compute_metadata_refresh
                # returns ONLY the two allowed keys (appetite_confidence,
                # appetite_last_updated).  Pass through MetadataRefreshDTO to
                # enforce the structural gate (FR-4).
                # The pipeline's payload.metadata_refresh already holds the final
                # desired values; use them directly rather than re-deriving.
                mr_payload = payload.get("metadata_refresh")
                if isinstance(mr_payload, dict):
                    dto = MetadataRefreshDTO(
                        appetite_confidence=mr_payload.get(
                            "appetite_confidence", refresh_fields["appetite_confidence"]
                        ),
                        appetite_last_updated=mr_payload.get(
                            "appetite_last_updated", refresh_fields["appetite_last_updated"]
                        ),
                    )
                else:
                    dto = MetadataRefreshDTO(**refresh_fields)

                try:
                    await CarrierProfileService.refresh_metadata(
                        session, ctx, carrier_id, dto
                    )
                    _log.info(
                        "carrier_appetite_batch: refreshed metadata for carrier=%r → confidence=%r",
                        carrier_id,
                        dto.appetite_confidence,
                    )
                except ValueError as exc:
                    # No profile row yet for this carrier — skip silently.
                    _log.debug(
                        "carrier_appetite_batch: refresh_metadata skipped for carrier=%r: %s",
                        carrier_id,
                        exc,
                    )
                    continue

                alerts.append(
                    MonitorAlertIn(
                        entity_ref=carrier_id,
                        alert_type="CI_METADATA_REFRESHED",
                        severity=SEVERITY_INFO,
                        payload={
                            "carrier_id": carrier_id,
                            "carrier_name": carrier_name,
                            "appetite_confidence": dto.appetite_confidence,
                            "appetite_last_updated": dto.appetite_last_updated,
                        },
                    )
                )

            # ── GENUINE_INCONSISTENCY (CI-04) ─────────────────────────────────
            elif pattern_type == "GENUINE_INCONSISTENCY":
                if await _pending_suggestion_exists(session, ctx.tenant_id, carrier_id):
                    _log.debug(
                        "carrier_appetite_batch: pending suggestion already exists for carrier=%r — skip",
                        carrier_id,
                    )
                    continue

                try:
                    await review_queue.enqueue(session, ctx, output, WORKFLOW_NAME)
                    _log.info(
                        "carrier_appetite_batch: enqueued GENUINE_INCONSISTENCY suggestion for carrier=%r",
                        carrier_id,
                    )
                except Exception as exc:
                    _log.warning(
                        "carrier_appetite_batch: enqueue failed for carrier=%r: %s",
                        carrier_id,
                        exc,
                    )
                    continue

                suggested_action: str = payload.get("suggested_action") or ""
                alerts.append(
                    MonitorAlertIn(
                        entity_ref=carrier_id,
                        alert_type="CI_SUGGESTION_CREATED",
                        severity=SEVERITY_WARN,
                        payload={
                            "carrier_id": carrier_id,
                            "carrier_name": carrier_name,
                            "suggestion_id": payload.get("suggestion_id"),
                            "class_code": payload.get("class_code"),
                            "class_level_inconsistent_count": (
                                len([
                                    e for e in payload.get("evidence", [])
                                    if e.get("reason_scope") == "class_level"
                                    and e.get("outcome") != "consistent"
                                ])
                            ),
                            "suggested_action_preview": (
                                suggested_action[:200] if suggested_action else None
                            ),
                        },
                    )
                )

            # ── INSUFFICIENT_SIGNAL (CI-05) ───────────────────────────────────
            else:
                # Correct default: produce nothing.
                _log.debug(
                    "carrier_appetite_batch: INSUFFICIENT_SIGNAL for carrier=%r — suppressed",
                    carrier_id,
                )

        return alerts


# ── Registration ───────────────────────────────────────────────────────────────

register_monitor(_CarrierAppetiteBatchMonitor())

_log.debug("carrier_appetite_batch monitor registered")
