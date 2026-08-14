"""Routes under /api/mga/claims-intake — list, detail, run (triage an FNOL), act.
Human-in-the-loop; no auto-routing dispatch, no auto-settlement — every triage
decision is a proposed routing that a human sends on."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.db import get_session
from core.review_queue import AuthorityError
from core.tenancy import get_ctx
from verticals.mga.claims_intake.schema import ActRequest, ClaimsIntakeDetail, ClaimsIntakeRow
from verticals.mga.claims_intake.service import ClaimsIntakeService

router = APIRouter(prefix="/claims-intake", tags=["mga:claims-intake"])
_service = ClaimsIntakeService()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CtxDep = Annotated[Ctx, Depends(get_ctx)]


@router.get("", response_model=list[ClaimsIntakeRow])
async def list_claims(session: SessionDep, ctx: CtxDep) -> list[ClaimsIntakeRow]:
    return await _service.list_rows(session, ctx)


@router.post("/run", response_model=ClaimsIntakeDetail)
async def run_claims_intake(
    session: SessionDep, ctx: CtxDep, scenario: str
) -> ClaimsIntakeDetail:
    """Dev/ingestion trigger: triage one fixture scenario (or dataset scenario name)."""
    try:
        return await _service.process(session, ctx, scenario)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/export-sheet")
async def export_claims_to_sheet(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: exports every claim currently in this tenant's
    list — regardless of review status — to the connected spreadsheet.
    Registered before "/{submission_id}" so "export-sheet" is never matched as
    a submission id."""
    status_str = await _service.export_all_to_sheet(session, ctx)
    return {"status": status_str}


@router.post("/export-drive")
async def export_claims_to_drive(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: generates one PDF covering every claim
    currently in this tenant's list and uploads it to the connected Drive."""
    status_str = await _service.export_all_to_drive(session, ctx)
    return {"status": status_str}


@router.get("/{submission_id}", response_model=ClaimsIntakeDetail)
async def get_claims_intake(
    session: SessionDep, ctx: CtxDep, submission_id: str
) -> ClaimsIntakeDetail:
    detail = await _service.get_detail(session, ctx, submission_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "claims intake record not found")
    return detail


@router.post("/{submission_id}/act")
async def act_on_claims_intake(
    session: SessionDep, ctx: CtxDep, submission_id: str, body: ActRequest
) -> dict[str, str]:
    """Human action: approve (confirm triage) | send (dispatch to carrier/TPA) | escalate."""
    try:
        return await _service.act(session, ctx, submission_id, body.action, body.note)
    except AuthorityError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
