"""Shared Google Drive write-back helper — archives a real copy of the issued
policy document to a tenant's connected Drive once Binder & Policy Issuance
verifies it matches what was bound, mirroring ``writeback.py``'s Sheets
write-back precedent exactly: a fallback nicety, never a hard dependency. A
missing/unconnected Drive integration must never fail the caller's primary
action (attaching the issued policy), so this always returns a status string
instead of raising.
"""

from __future__ import annotations

import logging

from core.common.dtos import Ctx
from core.ingestion.connectors import ConnectorNotConnectedError, ConnectorService

log = logging.getLogger(__name__)

DriveWriteBackStatus = str  # "ok" | "skipped-no-content" | "skipped-not-connected" | "failed"


async def try_archive_document(
    connector: ConnectorService, ctx: Ctx, *, filename: str, content: str | None,
) -> DriveWriteBackStatus:
    """Write-back is a fallback, not a hard dependency — no failure here may
    ever propagate to the caller (attaching the issued policy must always
    succeed on its own terms). Catches ``ConnectorNotConnectedError`` (no
    Drive connection yet) and any transport/HTTP failure from the Nango proxy
    itself, logged so it's diagnosable, never raised."""
    if not content:
        return "skipped-no-content"
    try:
        await connector.upload_file(ctx, filename=filename, content=content)
    except ConnectorNotConnectedError:
        return "skipped-not-connected"
    except Exception:
        log.exception(
            "Drive archive write-back failed (tenant=%s, filename=%s)", ctx.tenant_id, filename,
        )
        return "failed"
    return "ok"
