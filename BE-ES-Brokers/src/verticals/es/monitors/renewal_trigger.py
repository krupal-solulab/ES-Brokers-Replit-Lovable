"""Scheduled monitor for the Renewal Remarketing workflow — G5.

One monitor registered here:
  renewal_trigger   FR-1 / FR-7 / FR-8 / FR-9 / FR-19

KB06 in force: ALL renewal decision logic delegates to
``RenewalRemarketingPipeline.run_live()`` — the identical entry point used
by the router's ``/run-live`` endpoint.  The monitor only decides WHICH
bind_ids to trigger; it never re-derives a trigger level.

What the monitor does per run
-----------------------------
1. Load all binder_issuance OutputPackages for this tenant.
2. Load all existing renewal_remarketing trigger-stage reviews (idempotency set).
3. For each bound policy whose expiration is within the configured window and
   that does NOT already have a current-cycle trigger-stage review:
   a. Call ``RenewalRemarketingPipeline.run_live(ctx, session, bind_id)``
      (live-data path: endorsement history, incumbent-offer inbox check,
      real remarketing history — all degrade gracefully when connectors
      are not live, per live_ingestion.py's own design).
   b. Enqueue the result via ``DefaultReviewQueueService``.
   c. Emit an URGENT RENEWAL_URGENT_REMARKET MonitorAlert if trigger level
      is URGENT_REMARKET (RR-07 non-response / lapse-risk — FR-8).
   d. Attempt a Slack notification, same as the router's /run-live does —
      never raises; a missing integration must not block the monitor.

Idempotency
-----------
"Current-cycle renewal review already exists" = any non-comparison-stage
renewal_remarketing OutputPackage whose payload.bind_id matches.  One
pipeline call per bind_id per renewal cycle.

URGENT_REMARKET alert deduplication
------------------------------------
The MonitorAlert is emitted exactly WHEN the pipeline runs (which is once
per bind_id per cycle — the idempotency check prevents re-running).  The
infra's as_of_day dedupe_key prevents double-writes within the same day.

First-cycle accounts (FR-11 / RR-08)
--------------------------------------
``parse_remarketing_history(None)`` → ``suppress=False`` → no suppressive
effect.  This is already in the engine; the monitor passes the same
``build_live_renewal_context`` output verbatim (KB06).

Exposure change already endorsed (Scenario 03)
------------------------------------------------
``build_live_renewal_context`` already sets ``already_endorsed=True`` in
the exposure_change dict when a material endorsement exists — the engine's
``detect_exposure_change`` fires the LIGHT_REMARKET_CHECK path instead of
treating it as new information.  No change needed here.

Window config
-------------
``get_effective_setting(tenant_id, "renewal_trigger_window_days", 90)``
respects the Admin Panel per-tenant override system.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.admin.settings_override import get_effective_setting
from core.common.dtos import Ctx
from core.config import get_settings
from core.ingestion.connectors import build_connector_service
from core.ingestion.slack_writeback import resolve_channel_id, try_notify_slack
from core.jobs.monitor import SEVERITY_URGENT, MonitorAlertIn, register_monitor
from core.llm import build_llm_service
from core.models import OutputPackage as OutputPackageRow
from core.review_queue import DefaultReviewQueueService
from verticals.es.workflows.renewal_remarketing.live_ingestion import (
    _bind_expiration_and_premium,  # private helper — same package
)
from verticals.es.workflows.renewal_remarketing.service import (
    WORKFLOW_NAME,
    RenewalRemarketingPipeline,
)

_log = logging.getLogger(__name__)

_WINDOW_SETTING_KEY = "renewal_trigger_window_days"
_DEFAULT_WINDOW_DAYS = 90


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _binder_payloads(session: AsyncSession, tenant_id: str) -> list[dict[str, Any]]:
    """All binder_issuance payloads that have a bind_id, for this tenant."""
    rows = (
        await session.execute(
            select(OutputPackageRow).where(
                col(OutputPackageRow.tenant_id) == tenant_id,
                col(OutputPackageRow.workflow) == "binder_issuance",
            )
        )
    ).scalars().all()
    return [
        dict(r.payload)
        for r in rows
        if r.payload and r.payload.get("bind_id")
    ]


async def _existing_trigger_review_bind_ids(
    session: AsyncSession, tenant_id: str
) -> set[str]:
    """bind_ids that already have a current-cycle trigger-stage renewal review."""
    rows = (
        await session.execute(
            select(OutputPackageRow).where(
                col(OutputPackageRow.tenant_id) == tenant_id,
                col(OutputPackageRow.workflow) == WORKFLOW_NAME,
            )
        )
    ).scalars().all()
    result: set[str] = set()
    for row in rows:
        if not row.payload:
            continue
        if row.payload.get("is_comparison_stage"):
            continue  # comparison-stage rows share the same bind_id — skip
        bid = row.payload.get("bind_id")
        if bid:
            result.add(bid)
    return result


async def _slack_notify_urgent(
    session: AsyncSession, ctx: Ctx, payload: dict[str, Any]
) -> None:
    """Best-effort Slack notification for URGENT_REMARKET — never raises.
    Mirrors the router's ``_maybe_notify_urgent_remarket`` helper exactly,
    but as a standalone function so the monitor avoids importing from the
    router module (dependency inversion)."""
    try:
        channel_id = await resolve_channel_id(session, ctx.tenant_id, get_settings())
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        text = (
            f"URGENT_REMARKET: {payload.get('named_insured') or 'A policy'} "
            f"(incumbent: {payload.get('incumbent_carrier_name') or 'unknown'}) — "
            "the incumbent hasn't responded with renewal terms and time is running short. "
            "Check Renewal Remarketing. [scheduled scan]"
        )
        await try_notify_slack(connector, ctx, channel_id, text)
    except Exception as exc:
        _log.debug("Slack notification skipped for URGENT_REMARKET: %s", exc)


# ── Monitor ────────────────────────────────────────────────────────────────────

class _RenewalTriggerMonitor:
    """FR-1 / FR-7 / FR-8 / FR-9 / FR-19 — scheduled renewal-review trigger.

    Populates the renewal review queue on a recurring schedule so that bound
    policies are reviewed without requiring a broker to manually click
    "Check live renewal" — the on-demand path the router exposes is still
    available; this monitor adds the proactive layer FR-19 requires.
    """

    name = "renewal_trigger"
    workflow = WORKFLOW_NAME

    async def run(
        self,
        session: AsyncSession,
        ctx: Ctx,
        as_of: date,
    ) -> list[MonitorAlertIn]:
        alerts: list[MonitorAlertIn] = []

        window_days = int(
            get_effective_setting(ctx.tenant_id, _WINDOW_SETTING_KEY, _DEFAULT_WINDOW_DAYS)
        )

        # One query each — avoid N+1 inside the per-bind loop.
        binder_payloads = await _binder_payloads(session, ctx.tenant_id)
        already_reviewed = await _existing_trigger_review_bind_ids(session, ctx.tenant_id)

        for bp in binder_payloads:
            bind_id: str = bp["bind_id"]

            # ── Idempotency: skip if trigger-stage review already exists ─────
            if bind_id in already_reviewed:
                continue

            # ── Expiration window check ───────────────────────────────────────
            expiration_date, _ = _bind_expiration_and_premium(bp)
            if expiration_date is None:
                continue
            days_until = (expiration_date - as_of).days
            if days_until < 0 or days_until > window_days:
                # Already expired or too far out — not in scope this cycle.
                continue

            # ── Run the pipeline (KB06 — all trigger logic stays in engine) ──
            try:
                pipeline = RenewalRemarketingPipeline(llm=build_llm_service())
                output = await pipeline.run_live(ctx, session, bind_id)
            except Exception as exc:
                _log.warning(
                    "renewal_trigger: pipeline.run_live failed for bind_id=%s: %s",
                    bind_id,
                    exc,
                )
                continue

            # ── Persist the review item ───────────────────────────────────────
            try:
                review_queue = DefaultReviewQueueService()
                await review_queue.enqueue(session, ctx, output, WORKFLOW_NAME)
            except Exception as exc:
                _log.warning(
                    "renewal_trigger: enqueue failed for bind_id=%s: %s", bind_id, exc
                )
                continue

            # ── URGENT_REMARKET: Slack + MonitorAlert (FR-8) ─────────────────
            trigger_level: str = (
                (output.payload.get("trigger_decision") or {}).get("level") or "NO_REMARKET"
            )
            if trigger_level == "URGENT_REMARKET":
                await _slack_notify_urgent(session, ctx, output.payload)

                reasoning_summary: str = (
                    (output.payload.get("trigger_decision") or {})
                    .get("reasoning", {})
                    .get("summary", "")
                    if isinstance(
                        (output.payload.get("trigger_decision") or {}).get("reasoning"),
                        dict,
                    )
                    else str(
                        (output.payload.get("trigger_decision") or {}).get("reasoning", "")
                    )
                )
                alerts.append(
                    MonitorAlertIn(
                        entity_ref=bind_id,
                        alert_type="RENEWAL_URGENT_REMARKET",
                        severity=SEVERITY_URGENT,
                        payload={
                            # Verbatim engine output — KB06.
                            "bind_id": bind_id,
                            "named_insured": output.payload.get("named_insured"),
                            "incumbent_carrier_name": output.payload.get(
                                "incumbent_carrier_name"
                            ),
                            "trigger_reasoning": reasoning_summary,
                            "expiration_date": expiration_date.isoformat(),
                            "days_until_expiration": days_until,
                        },
                    )
                )

        return alerts


# ── Registration ───────────────────────────────────────────────────────────────

register_monitor(_RenewalTriggerMonitor())

_log.debug("renewal_trigger monitor registered")
