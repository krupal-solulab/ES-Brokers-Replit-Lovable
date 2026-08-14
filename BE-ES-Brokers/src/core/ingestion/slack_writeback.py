"""Shared Slack write-back helper — posts a real notification to a tenant's
connected Slack channel, mirroring ``writeback.py``'s Sheets write-back
precedent exactly: a fallback nicety, never a hard dependency. A missing
channel id or unconnected Slack integration must never fail the caller's
primary action, so this always returns a status string instead of raising.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.config import Settings
from core.ingestion.connectors import ConnectorNotConnectedError, ConnectorService

log = logging.getLogger(__name__)

SlackWriteBackStatus = str  # "ok" | "skipped-no-channel-id" | "skipped-not-connected" | "failed"


async def resolve_channel_id(session: AsyncSession, tenant_id: str, settings: Settings) -> str:
    """The tenant's notification target, set on the Integrations page once
    Slack is connected (``Connection.channel_id``, provider=slack) — never a
    global env/config value, since each tenant picks their own channel. Same
    precedent as ``writeback.resolve_sheet_id``."""
    from core.integrations.repository import get_connection  # avoids import-time cycle

    conn = await get_connection(session, tenant_id, settings.nango_integration_slack)
    return (conn.channel_id or "") if conn is not None else ""


async def try_notify_slack(
    connector: ConnectorService, ctx: Ctx, channel_id: str, text: str,
) -> SlackWriteBackStatus:
    """Write-back is a fallback, not a hard dependency — no failure here may
    ever propagate to the caller. Catches ``ConnectorNotConnectedError`` (no
    Slack connection yet) and any transport/HTTP failure from the Nango proxy
    itself, logged so it's diagnosable, never raised."""
    if not channel_id:
        return "skipped-no-channel-id"
    try:
        await connector.send_slack_message(ctx, channel=channel_id, text=text)
    except ConnectorNotConnectedError:
        return "skipped-not-connected"
    except Exception:
        log.exception(
            "Slack notification write-back failed (tenant=%s, channel=%s)",
            ctx.tenant_id, channel_id,
        )
        return "failed"
    return "ok"
