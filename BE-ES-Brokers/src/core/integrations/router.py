"""Routes under ``/api/core/integrations`` — the tenant-facing "Connect Gmail" flow.

The frontend calls ``POST /connect-session`` to get a Nango Connect UI session
token, opens Nango's hosted popup with it, then calls ``POST /connections`` with
the ``connectionId`` Nango hands back on success. See docs/CONNECTORS_NANGO.md.
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.db import get_session
from core.ingestion import extract_folder_id, extract_sheet_id
from core.integrations.repository import get_connection, list_connections, upsert_connection
from core.tenancy.dependencies import get_ctx
from core.common.dtos import Ctx

router = APIRouter(prefix="/integrations", tags=["core:integrations"])

CtxDep = Annotated[Ctx, Depends(get_ctx)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class ConnectSessionRequest(BaseModel):
    provider: str


class ConnectSessionOut(BaseModel):
    session_token: str
    expires_at: str | None = None


class ConfirmConnectionRequest(BaseModel):
    provider: str
    nango_connection_id: str


class ConnectionOut(BaseModel):
    provider: str
    status: str
    sheet_id: str | None = None
    folder_id: str | None = None
    channel_id: str | None = None


class SheetIdRequest(BaseModel):
    sheet_id: str


class FolderIdRequest(BaseModel):
    folder_id: str


class ChannelIdRequest(BaseModel):
    channel_id: str


@router.post("/connect-session", status_code=status.HTTP_201_CREATED)
async def create_connect_session(
    body: ConnectSessionRequest,
    ctx: CtxDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConnectSessionOut:
    """Mints a Nango Connect UI session token scoped to this tenant + the
    requested integration, so the frontend can open the hosted OAuth popup.
    ``provider`` must be one of this deployment's known Nango integration
    keys (Gmail/Sheets/Drive/Calendar/Slack/QuickBooks) — never passed
    through to Nango unchecked."""
    known_providers = {
        settings.nango_integration_mail,
        settings.nango_integration_sheet,
        settings.nango_integration_drive,
        settings.nango_integration_calendar,
        settings.nango_integration_slack,
        settings.nango_integration_quickbooks,
    }
    if body.provider not in known_providers:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown provider: {body.provider}")
    if not settings.nango_secret_key:
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED, "NANGO_SECRET_KEY is not configured"
        )
    async with httpx.AsyncClient(base_url=settings.nango_host, timeout=30.0) as client:
        resp = await client.post(
            "/connect/sessions",
            headers={"Authorization": f"Bearer {settings.nango_secret_key}"},
            json={
                "end_user": {"id": ctx.tenant_id},
                "allowed_integrations": [body.provider],
            },
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Nango connect-session request failed: {resp.text}"
        )
    data = resp.json().get("data", {})
    return ConnectSessionOut(session_token=data.get("token", ""), expires_at=data.get("expires_at"))


@router.post("/connections", status_code=status.HTTP_201_CREATED)
async def confirm_connection(
    body: ConfirmConnectionRequest, ctx: CtxDep, session: SessionDep
) -> ConnectionOut:
    """Called by the frontend right after the Nango Connect UI popup reports
    success — persists the tenant <-> provider <-> nango_connection_id mapping."""
    row = await upsert_connection(
        session,
        ctx.tenant_id,
        body.provider,
        nango_connection_id=body.nango_connection_id,
        status="connected",
    )
    return ConnectionOut(
        provider=row.provider, status=row.status, sheet_id=row.sheet_id, folder_id=row.folder_id, channel_id=row.channel_id
    )


@router.get("/connections")
async def get_connections(ctx: CtxDep, session: SessionDep) -> list[ConnectionOut]:
    rows = await list_connections(session, ctx.tenant_id)
    return [
        ConnectionOut(provider=r.provider, status=r.status, sheet_id=r.sheet_id, folder_id=r.folder_id, channel_id=r.channel_id)
        for r in rows
    ]


@router.post("/connections/{provider}/disconnect")
async def disconnect(provider: str, ctx: CtxDep, session: SessionDep) -> ConnectionOut:
    row = await upsert_connection(session, ctx.tenant_id, provider, status="disconnected")
    return ConnectionOut(
        provider=row.provider, status=row.status, sheet_id=row.sheet_id, folder_id=row.folder_id, channel_id=row.channel_id
    )


@router.patch("/connections/{provider}/sheet-id")
async def set_sheet_id(
    provider: str,
    body: SheetIdRequest,
    ctx: CtxDep,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConnectionOut:
    """Sets the tenant's target spreadsheet for the Sheets write-back fallback
    (Bind Issuance/Bordereau Reporting/Renewal Management, on approve — see
    docs/CONNECTORS_NANGO.md). Only the Sheets provider carries a sheet id, and
    only once the account is actually connected — pasting a sheet id before
    connecting would silently do nothing useful.

    Accepts either a bare spreadsheet ID or the full URL a tenant would naturally
    copy from their browser (``extract_sheet_id`` pulls the ID out either way) —
    storing the raw URL would silently break every write-back call, since the
    Sheets proxy needs the bare ID in its path."""
    if provider != settings.nango_integration_sheet:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"provider '{provider}' does not use a sheet id"
        )
    row = await get_connection(session, ctx.tenant_id, provider)
    if row is None or row.status != "connected":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "connect Google Sheets before setting a sheet id"
        )
    sheet_id = extract_sheet_id(body.sheet_id)
    if not sheet_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "sheet_id may not be empty")
    updated = await upsert_connection(session, ctx.tenant_id, provider, sheet_id=sheet_id)
    return ConnectionOut(
        provider=updated.provider, status=updated.status,
        sheet_id=updated.sheet_id, folder_id=updated.folder_id,
    )


@router.patch("/connections/{provider}/folder-id")
async def set_folder_id(
    provider: str,
    body: FolderIdRequest,
    ctx: CtxDep,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConnectionOut:
    """Sets the tenant's target Drive folder for the "Upload to Drive" action
    (Bind Issuance/Bordereau Reporting/Renewal Management — see
    docs/CONNECTORS_NANGO.md). Only the Drive provider carries a folder id, and
    only once the account is actually connected. Optional: uploads land in the
    tenant's Drive root if never set — this is an organizational nicety, not a
    hard requirement, same as Sheets' write-back-is-a-fallback philosophy.

    Accepts either a bare folder ID or the full URL a tenant would naturally
    copy from their browser (``extract_folder_id`` pulls the ID out either way)."""
    if provider != settings.nango_integration_drive:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"provider '{provider}' does not use a folder id"
        )
    row = await get_connection(session, ctx.tenant_id, provider)
    if row is None or row.status != "connected":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "connect Google Drive before setting a folder id"
        )
    folder_id = extract_folder_id(body.folder_id)
    if not folder_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "folder_id may not be empty")
    updated = await upsert_connection(session, ctx.tenant_id, provider, folder_id=folder_id)
    return ConnectionOut(
        provider=updated.provider, status=updated.status,
        sheet_id=updated.sheet_id, folder_id=updated.folder_id,
    )


@router.patch("/connections/{provider}/channel-id")
async def set_channel_id(
    provider: str,
    body: ChannelIdRequest,
    ctx: CtxDep,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConnectionOut:
    """Sets the tenant's target Slack channel for the notification fallback
    (Renewal Remarketing's URGENT_REMARKET alert — see
    docs/CONNECTORS_NANGO.md). Only the Slack provider carries a channel id,
    and only once the account is actually connected — same precedent as
    ``set_sheet_id`` above."""
    if provider != settings.nango_integration_slack:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"provider '{provider}' does not use a channel id"
        )
    row = await get_connection(session, ctx.tenant_id, provider)
    if row is None or row.status != "connected":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "connect Slack before setting a channel id"
        )
    channel_id = body.channel_id.strip()
    if not channel_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "channel_id may not be empty")
    updated = await upsert_connection(session, ctx.tenant_id, provider, channel_id=channel_id)
    return ConnectionOut(
        provider=updated.provider, status=updated.status, sheet_id=updated.sheet_id,
        channel_id=updated.channel_id,
    )
