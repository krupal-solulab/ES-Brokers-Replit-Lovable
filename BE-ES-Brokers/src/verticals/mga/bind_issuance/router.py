"""Routes under /api/mga/bind-issuance — list, detail, run (process a bind instruction
or issuance confirmation), act. Human approves every bind order and resolves every
flagged discrepancy; no auto-binding, no auto-resolved discrepancy."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.db import get_session
from core.review_queue import AuthorityError
from core.tenancy import get_ctx
from verticals.mga.bind_issuance.schema import ActRequest, BindDetail, BindRow
from verticals.mga.bind_issuance.service import BindIssuanceService

router = APIRouter(prefix="/bind-issuance", tags=["mga:bind-issuance"])
_service = BindIssuanceService()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CtxDep = Annotated[Ctx, Depends(get_ctx)]


@router.get("", response_model=list[BindRow])
async def list_binds(session: SessionDep, ctx: CtxDep) -> list[BindRow]:
    return await _service.list_rows(session, ctx)


@router.post("/run", response_model=BindDetail)
async def run_bind(session: SessionDep, ctx: CtxDep, scenario: str) -> BindDetail:
    """Dev/ingestion trigger: process one fixture scenario (bind instruction or
    issuance confirmation)."""
    try:
        return await _service.process(session, ctx, scenario)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/run-from-quoting", response_model=BindDetail)
async def run_bind_from_quoting(
    session: SessionDep, ctx: CtxDep, submission_id: str
) -> BindDetail:
    """Real trigger per the PRD: generate a bind order from a Quoting & Rating worksheet
    the underwriter has already finalized (approved) — never a worksheet still pending."""
    try:
        return await _service.process_from_quoting(session, ctx, submission_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/export-sheet")
async def export_binds_to_sheet(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: exports every bind order currently in this
    tenant's list — regardless of review status — to the connected spreadsheet."""
    status_str = await _service.export_all_to_sheet(session, ctx)
    return {"status": status_str}


@router.post("/export-drive")
async def export_binds_to_drive(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: generates one PDF covering every bind order
    currently in this tenant's list and uploads it to the connected Drive."""
    status_str = await _service.export_all_to_drive(session, ctx)
    return {"status": status_str}


@router.get("/{submission_id}", response_model=BindDetail)
async def get_bind(session: SessionDep, ctx: CtxDep, submission_id: str) -> BindDetail:
    detail = await _service.get_detail(session, ctx, submission_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bind order not found")
    return detail


@router.post("/{submission_id}/act")
async def act_on_bind(
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


@router.post("/{submission_id}/obligations/{obligation_index}/add-to-calendar")
async def add_obligation_to_calendar(
    session: SessionDep, ctx: CtxDep, submission_id: str, obligation_index: int,
) -> dict[str, str]:
    """Manual, per-item, per-obligation: creates/updates one all-day Google
    Calendar event for this one post-bind obligation on this one bind order."""
    try:
        status_str = await _service.add_obligation_to_calendar(
            session, ctx, submission_id, obligation_index)
        return {"status": status_str}
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
