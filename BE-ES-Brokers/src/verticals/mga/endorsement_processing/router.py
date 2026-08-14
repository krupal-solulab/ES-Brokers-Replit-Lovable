"""Routes under /api/mga/endorsement-processing — list, detail, run (process a change
request), act. Human-in-the-loop; no auto-processing, no auto-referral outcome."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.db import get_session
from core.ingestion.connectors import ConnectorNotConnectedError
from core.review_queue import AuthorityError
from core.tenancy import get_ctx
from verticals.mga.endorsement_processing.schema import (
    ActRequest,
    EndorsementDetail,
    EndorsementRow,
    InboxRow,
)
from verticals.mga.endorsement_processing.service import EndorsementService

router = APIRouter(prefix="/endorsement-processing", tags=["mga:endorsement-processing"])
_service = EndorsementService()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CtxDep = Annotated[Ctx, Depends(get_ctx)]


@router.get("", response_model=list[EndorsementRow])
async def list_endorsements(session: SessionDep, ctx: CtxDep) -> list[EndorsementRow]:
    return await _service.list_rows(session, ctx)


@router.get("/inbox", response_model=list[InboxRow])
async def list_inbox(session: SessionDep, ctx: CtxDep) -> list[InboxRow]:
    """Live, unfiltered mailbox — every message matching the inbox query (mock
    fixtures or real Gmail via Nango, per CONNECTORS_MODE), each flagged with
    whether it has already been processed. Use ``POST /run-live`` to process one."""
    try:
        return await _service.list_inbox(session, ctx)
    except ConnectorNotConnectedError as exc:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            f"no active connection for provider '{exc.provider}' — connect Gmail first",
        ) from exc


@router.post("/run", response_model=EndorsementDetail)
async def run_endorsement(session: SessionDep, ctx: CtxDep, scenario: str) -> EndorsementDetail:
    """Dev/ingestion trigger: process one fixture scenario (or dataset scenario name)."""
    try:
        return await _service.process(session, ctx, scenario)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/run-live", response_model=EndorsementDetail)
async def run_endorsement_live(
    session: SessionDep, ctx: CtxDep, message_id: str
) -> EndorsementDetail:
    """Process one real Gmail message: extracts policy_number/named_insured/
    requested_change from the email, resolves delegated_authority/rate_plan_reference
    from the (stubbed) policy lookup, then runs the same engine as /run."""
    try:
        return await _service.process_live(session, ctx, message_id)
    except ConnectorNotConnectedError as exc:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            f"no active connection for provider '{exc.provider}' — connect Gmail first",
        ) from exc


@router.post("/export-sheet")
async def export_endorsements_to_sheet(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: exports every endorsement currently in this
    tenant's list — regardless of review status — to the connected spreadsheet.
    Registered before "/{submission_id}" so "export-sheet" is never matched as a
    submission id."""
    status_str = await _service.export_all_to_sheet(session, ctx)
    return {"status": status_str}


@router.post("/export-drive")
async def export_endorsements_to_drive(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: generates one PDF covering every endorsement
    currently in this tenant's list and uploads it to the connected Drive."""
    status_str = await _service.export_all_to_drive(session, ctx)
    return {"status": status_str}


@router.get("/{submission_id}", response_model=EndorsementDetail)
async def get_endorsement(
    session: SessionDep, ctx: CtxDep, submission_id: str
) -> EndorsementDetail:
    detail = await _service.get_detail(session, ctx, submission_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "endorsement not found")
    return detail


@router.post("/{submission_id}/act")
async def act_on_endorsement(
    session: SessionDep, ctx: CtxDep, submission_id: str, body: ActRequest
) -> dict[str, str]:
    """Human action: approve (issue) | send (carrier referral) | escalate."""
    try:
        return await _service.act(session, ctx, submission_id, body.action, body.note)
    except AuthorityError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
