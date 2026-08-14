"""Shared Google Calendar write-back helper — creates a real renewal-reminder
event on a tenant's connected Calendar, mirroring ``writeback.py``'s Sheets
write-back precedent exactly: a fallback nicety, never a hard dependency. A
missing/unconnected Calendar integration must never fail the caller's primary
action (confirming a bind), so this always returns a status string instead of
raising.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from core.common.dtos import Ctx
from core.ingestion.connectors import ConnectorNotConnectedError, ConnectorService

log = logging.getLogger(__name__)

CalendarWriteBackStatus = str  # "ok" | "skipped-no-date" | "skipped-not-connected" | "failed"

# How many days before expiration the reminder is set — same order of
# magnitude as remarket_engine.py's own NON_RESPONSE_URGENT_DAYS_THRESHOLD (30),
# but this fires earlier since it's a "go check" nudge, not an urgency signal.
RENEWAL_REMINDER_DAYS_BEFORE_EXPIRATION = 60


async def try_create_renewal_reminder(
    connector: ConnectorService, ctx: Ctx, *, named_insured: str, carrier_name: str,
    expiration_date: str | None,
) -> CalendarWriteBackStatus:
    """Write-back is a fallback, not a hard dependency — no failure here may
    ever propagate to the caller (confirming a bind must always succeed on its
    own terms). Catches ``ConnectorNotConnectedError`` (no Calendar connection
    yet) and any transport/HTTP failure from the Nango proxy itself, logged so
    it's diagnosable, never raised."""
    if not expiration_date:
        return "skipped-no-date"
    try:
        reminder_date = date.fromisoformat(expiration_date) - timedelta(
            days=RENEWAL_REMINDER_DAYS_BEFORE_EXPIRATION
        )
    except ValueError:
        return "skipped-no-date"

    summary = f"{named_insured} — renewal check ({carrier_name})"
    description = (
        f"Policy for {named_insured} (bound with {carrier_name}) expires on "
        f"{expiration_date}. Check Renewal Remarketing to see if it's worth "
        "shopping around before it renews."
    )
    try:
        await connector.create_event(
            ctx, summary=summary, description=description,
            start_date=reminder_date.isoformat(),
            end_date=(reminder_date + timedelta(days=1)).isoformat(),
        )
    except ConnectorNotConnectedError:
        return "skipped-not-connected"
    except Exception:
        log.exception(
            "Calendar renewal-reminder write-back failed (tenant=%s, named_insured=%s)",
            ctx.tenant_id, named_insured,
        )
        return "failed"
    return "ok"


async def try_create_obligation_reminder(
    connector: ConnectorService, ctx: Ctx, *, named_insured: str, description: str,
    due_date: str | None,
) -> CalendarWriteBackStatus:
    """Broker-triggered manual reminder for one post-bind ongoing obligation
    (BI-07) — same fallback-nicety precedent as ``try_create_renewal_reminder``
    above, but manual rather than automatic: BI-07 requires these obligation
    reminders be "surfaced to the broker, not automatically actioned," unlike
    the renewal-check reminder above (a different trigger entirely). Fires on
    the obligation's own due date, no offset. Never raises — a missing/
    unconnected Calendar integration must never fail the caller's action."""
    if not due_date:
        return "skipped-no-date"
    try:
        due = date.fromisoformat(due_date)
    except ValueError:
        return "skipped-no-date"

    summary = f"{named_insured} — obligation due: {description}"
    event_description = f"Post-bind obligation for {named_insured}: {description} (due {due_date})."
    try:
        await connector.create_event(
            ctx, summary=summary, description=event_description,
            start_date=due.isoformat(), end_date=(due + timedelta(days=1)).isoformat(),
        )
    except ConnectorNotConnectedError:
        return "skipped-not-connected"
    except Exception:
        log.exception(
            "Calendar obligation-reminder write-back failed (tenant=%s, named_insured=%s)",
            ctx.tenant_id, named_insured,
        )
        return "failed"
    return "ok"
