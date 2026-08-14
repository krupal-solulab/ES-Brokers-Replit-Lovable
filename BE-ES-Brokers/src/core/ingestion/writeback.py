"""Shared Sheets write-back and Drive-upload helpers — the fallback paths used when
a workflow has no PAS integration (Sheets) or no persisted source document (Drive),
see docs/CONNECTORS_NANGO.md. Both are fallbacks, not hard dependencies — a missing
sheet/folder id or an unconnected integration must never fail the caller's primary
action, so these always return a status string instead of raising.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.config import Settings
from core.ingestion.connectors import ConnectorNotConnectedError, ConnectorService

log = logging.getLogger(__name__)

WriteBackStatus = str  # "ok" | "skipped-no-sheet-id" | "skipped-not-connected" | "failed"
UploadStatus = str  # "ok" | "skipped-not-connected" | "failed"  (no-folder-id is NOT a skip — root Drive is a valid target)
CalendarStatus = str  # "ok" | "skipped-not-connected" | "failed"

_SHEET_URL_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
_FOLDER_URL_ID = re.compile(r"/folders/([a-zA-Z0-9-_]+)")


def extract_sheet_id(raw: str) -> str:
    """A tenant naturally copies the full URL from their browser's address bar, not
    the bare ID buried inside it — accept either. ``raw`` may be a bare spreadsheet
    ID or a full ``https://docs.google.com/spreadsheets/d/{ID}/edit...`` URL; returns
    just the ID either way. The Sheets API proxy needs the bare ID, never the URL —
    passing the raw URL through would silently break every write-back call."""
    match = _SHEET_URL_ID.search(raw)
    return match.group(1) if match is not None else raw.strip()


def extract_folder_id(raw: str) -> str:
    """Same URL-or-bare-ID acceptance as ``extract_sheet_id``, for a Drive folder
    (``https://drive.google.com/drive/folders/{ID}`` or the ``/drive/u/0/folders/{ID}``
    variant) — the Drive API's ``parents`` field needs the bare ID."""
    match = _FOLDER_URL_ID.search(raw)
    return match.group(1) if match is not None else raw.strip()


async def resolve_sheet_id(session: AsyncSession, tenant_id: str, settings: Settings) -> str:
    """The tenant's write-back target, set on the Integrations page once Sheets is
    connected (``Connection.sheet_id``, provider=google-sheet) — never a global
    env/config value, since each tenant picks their own spreadsheet."""
    from core.integrations.repository import get_connection  # avoids import-time cycle

    conn = await get_connection(session, tenant_id, settings.nango_integration_sheet)
    return (conn.sheet_id or "") if conn is not None else ""


async def resolve_drive_folder_id(session: AsyncSession, tenant_id: str, settings: Settings) -> str:
    """The tenant's upload target folder, set on the Integrations page once Drive is
    connected (``Connection.folder_id``, provider=google-drive). Empty string is a
    valid, expected value here (unlike Sheets) — it means "upload to Drive root,"
    not "skip the upload.\""""
    from core.integrations.repository import get_connection  # avoids import-time cycle

    conn = await get_connection(session, tenant_id, settings.nango_integration_drive)
    return (conn.folder_id or "") if conn is not None else ""


async def try_append_rows(
    connector: ConnectorService, ctx: Ctx, sheet_id: str, rows: list[list[Any]], *,
    tab: str, header: list[str] | None = None,
) -> WriteBackStatus:
    """Write-back is a fallback, not a hard dependency — no failure here may ever
    propagate to the caller (approving a review item must always succeed on its
    own terms). Catches ConnectorNotConnectedError (no Sheets connection yet) and
    any transport/HTTP failure from the Nango proxy itself (network error, or a
    non-2xx from Nango/Google — bad sheet id, expired auth, rate limit, including a
    failed tab-create/header-write when ``header`` is given) — logged so it's
    diagnosable, never raised. ``tab`` is the workflow's own named sheet/tab (e.g.
    "Bind Issuance") — each workflow writes into its own tab within the one shared
    spreadsheet, never a shared default tab."""
    if not sheet_id:
        return "skipped-no-sheet-id"
    try:
        await connector.append_rows(ctx, sheet_id, rows, tab=tab, header=header)
    except ConnectorNotConnectedError:
        return "skipped-not-connected"
    except httpx.HTTPError:
        log.exception(
            "Sheets write-back failed (tenant=%s, sheet_id=%s, tab=%s)",
            ctx.tenant_id, sheet_id, tab,
        )
        return "failed"
    return "ok"


async def try_put_file(
    connector: ConnectorService, ctx: Ctx, folder_id: str, filename: str,
    content: bytes, mime_type: str,
) -> UploadStatus:
    """Drive upload is manual (button-click) and never a hard dependency — no
    failure here may ever propagate to the caller. Catches ConnectorNotConnectedError
    (no Drive connection yet) and any transport/HTTP failure from the Nango proxy
    (network error, or a non-2xx from Nango/Google) — logged so it's diagnosable,
    never raised. An empty ``folder_id`` is NOT a skip condition, unlike Sheets'
    empty sheet_id — it just means "upload to the tenant's Drive root," a valid
    and expected default."""
    try:
        await connector.put_file(ctx, folder_id, filename, content, mime_type)
    except ConnectorNotConnectedError:
        return "skipped-not-connected"
    except httpx.HTTPError:
        log.exception(
            "Drive upload failed (tenant=%s, folder_id=%s, filename=%s)",
            ctx.tenant_id, folder_id, filename,
        )
        return "failed"
    return "ok"


async def try_create_event(
    connector: ConnectorService, ctx: Ctx, event_id: str, *,
    summary: str, description: str, start_date: str, end_date: str,
) -> CalendarStatus:
    """Calendar export is manual (button-click) and never a hard dependency — no
    failure here may ever propagate to the caller. Catches ConnectorNotConnectedError
    (no Calendar connection yet) and any transport/HTTP failure from the Nango proxy
    — logged so it's diagnosable, never raised. ``event_id`` must be a deterministic,
    caller-derived id (e.g. from the source item's own id) so a repeat click updates
    the same event instead of creating duplicates."""
    try:
        await connector.create_event(
            ctx, event_id, summary=summary, description=description,
            start_date=start_date, end_date=end_date,
        )
    except ConnectorNotConnectedError:
        return "skipped-not-connected"
    except httpx.HTTPStatusError as exc:
        log.exception(
            "Calendar event upsert failed (tenant=%s, event_id=%s, response=%s)",
            ctx.tenant_id, event_id, exc.response.text,
        )
        return "failed"
    except httpx.HTTPError:
        log.exception(
            "Calendar event upsert failed (tenant=%s, event_id=%s)", ctx.tenant_id, event_id,
        )
        return "failed"
    return "ok"
