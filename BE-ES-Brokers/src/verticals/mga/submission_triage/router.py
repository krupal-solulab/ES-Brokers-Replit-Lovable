"""Routes under /api/mga/submission-triage — list, detail, run, act.

Human-in-the-loop: ``act`` goes through the shared review queue (RBAC + authority cap);
``send`` (= request-info to broker) is human-triggered only — no auto-send anywhere.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.db import get_session
from core.ingestion.connectors import ConnectorNotConnectedError
from core.review_queue import AuthorityError
from core.tenancy import get_ctx
from verticals.mga.submission_triage.schema import (
    ActRequest,
    InboxRow,
    SubmissionRow,
    TriageDetail,
)
from verticals.mga.submission_triage.service import TriageService

router = APIRouter(prefix="/submission-triage", tags=["mga:submission-triage"])
_service = TriageService()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CtxDep = Annotated[Ctx, Depends(get_ctx)]


@router.get("", response_model=list[SubmissionRow])
async def list_submissions(session: SessionDep, ctx: CtxDep) -> list[SubmissionRow]:
    """Inbox — triaged submissions for the tenant."""
    return await _service.list_rows(session, ctx)


@router.get("/inbox", response_model=list[InboxRow])
async def list_inbox(session: SessionDep, ctx: CtxDep) -> list[InboxRow]:
    """Live, unfiltered mailbox — every message matching the inbox query (mock
    fixtures or real Gmail via Nango, per CONNECTORS_MODE), each flagged with
    whether it has already been triaged. Use ``POST /run`` to triage one."""
    try:
        return await _service.list_inbox(session, ctx)
    except ConnectorNotConnectedError as exc:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            f"no active connection for provider '{exc.provider}' — connect Gmail first",
        ) from exc


@router.post("/run", response_model=TriageDetail)
async def run_triage(session: SessionDep, ctx: CtxDep, message_id: str) -> TriageDetail:
    """Dev/ingestion trigger: run the pipeline for one fixture submission and persist.
    (In production the Arq ingestion job invokes the same service.)"""
    return await _service.triage(session, ctx, message_id)


@router.post("/export-sheet")
async def export_submissions_to_sheet(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: exports every submission currently in this
    tenant's list — regardless of review status — to the connected spreadsheet.
    Registered before "/{submission_id}" so "export-sheet" is never matched as a
    submission id."""
    status_str = await _service.export_all_to_sheet(session, ctx)
    return {"status": status_str}


@router.post("/export-drive")
async def export_submissions_to_drive(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: generates one PDF covering every submission
    currently in this tenant's list and uploads it to the connected Drive."""
    status_str = await _service.export_all_to_drive(session, ctx)
    return {"status": status_str}


@router.get("/{submission_id}", response_model=TriageDetail)
async def get_submission(session: SessionDep, ctx: CtxDep, submission_id: str) -> TriageDetail:
    detail = await _service.get_detail(session, ctx, submission_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "submission not found")
    return detail


@router.post("/{submission_id}/act")
async def act_on_submission(
    session: SessionDep, ctx: CtxDep, submission_id: str, body: ActRequest
) -> dict[str, str]:
    """Human action: approve | send (request-info to broker) | escalate."""
    try:
        return await _service.act(session, ctx, submission_id, body.action, body.amount, body.note)
    except AuthorityError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
