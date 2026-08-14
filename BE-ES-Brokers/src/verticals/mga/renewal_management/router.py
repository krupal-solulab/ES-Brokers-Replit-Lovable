"""Routes under /api/mga/renewal — list, detail, run, act. Human-in-the-loop; no auto-send."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.db import get_session
from core.ingestion.connectors import ConnectorNotConnectedError
from core.review_queue import AuthorityError
from core.tenancy import get_ctx
from verticals.mga.renewal_management.schema import (
    ActRequest,
    InboxRow,
    RenewalDetail,
    RenewalRow,
)
from verticals.mga.renewal_management.service import RenewalService

router = APIRouter(prefix="/renewal", tags=["mga:renewal-management"])
_service = RenewalService()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CtxDep = Annotated[Ctx, Depends(get_ctx)]


@router.get("", response_model=list[RenewalRow])
async def list_renewals(session: SessionDep, ctx: CtxDep) -> list[RenewalRow]:
    return await _service.list_rows(session, ctx)


@router.get("/inbox", response_model=list[InboxRow])
async def list_inbox(session: SessionDep, ctx: CtxDep) -> list[InboxRow]:
    """Live, unfiltered mailbox — every message matching the inbox query (mock
    fixtures or real Gmail via Nango, per CONNECTORS_MODE), each flagged with
    whether it has already been run through the renewal comparison. Use
    ``POST /run`` to process one."""
    try:
        return await _service.list_inbox(session, ctx)
    except ConnectorNotConnectedError as exc:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            f"no active connection for provider '{exc.provider}' — connect Gmail first",
        ) from exc


@router.post("/run", response_model=RenewalDetail)
async def run_renewal(session: SessionDep, ctx: CtxDep, message_id: str) -> RenewalDetail:
    """Dev/ingestion trigger: run the renewal comparison for one fixture case and persist."""
    return await _service.renew(session, ctx, message_id)


@router.post("/export-sheet")
async def export_renewals_to_sheet(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: exports every renewal currently in this tenant's
    list — regardless of review status — to the connected spreadsheet. Registered
    before "/{submission_id}" so "export-sheet" is never matched as a submission id."""
    status_str = await _service.export_all_to_sheet(session, ctx)
    return {"status": status_str}


@router.post("/export-drive")
async def export_renewals_to_drive(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: generates one PDF covering every renewal
    currently in this tenant's list and uploads it to the connected Drive."""
    status_str = await _service.export_all_to_drive(session, ctx)
    return {"status": status_str}


@router.get("/{submission_id}", response_model=RenewalDetail)
async def get_renewal(session: SessionDep, ctx: CtxDep, submission_id: str) -> RenewalDetail:
    detail = await _service.get_detail(session, ctx, submission_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "renewal not found")
    return detail


@router.post("/{submission_id}/act")
async def act_on_renewal(
    session: SessionDep, ctx: CtxDep, submission_id: str, body: ActRequest
) -> dict[str, str]:
    """Human action: approve | send (broker outreach) | escalate."""
    try:
        return await _service.act(session, ctx, submission_id, body.action, body.amount, body.note)
    except AuthorityError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/{submission_id}/add-to-calendar")
async def add_renewal_to_calendar(
    session: SessionDep, ctx: CtxDep, submission_id: str
) -> dict[str, str]:
    """Manual, per-item: creates/updates one all-day Google Calendar event for
    this one renewal, dated at its expiration date."""
    try:
        status_str = await _service.add_to_calendar(session, ctx, submission_id)
        return {"status": status_str}
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
