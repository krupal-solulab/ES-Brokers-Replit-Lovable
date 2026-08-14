"""Routes under /api/mga/bordereau-reporting — list, detail, run (compile a
bordereau), act. A bordereau is a formal filing under a contractual obligation to a
carrier partner; every compiled bordereau routes to a human-reviewed queue and is
never auto-submitted."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.db import get_session
from core.review_queue import AuthorityError
from core.tenancy import get_ctx
from verticals.mga.bordereau_reporting.schema import (
    ActRequest,
    BordereauDetail,
    BordereauRow,
)
from verticals.mga.bordereau_reporting.service import BordereauService

router = APIRouter(prefix="/bordereau-reporting", tags=["mga:bordereau-reporting"])
_service = BordereauService()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CtxDep = Annotated[Ctx, Depends(get_ctx)]


@router.get("", response_model=list[BordereauRow])
async def list_bordereaux(session: SessionDep, ctx: CtxDep) -> list[BordereauRow]:
    return await _service.list_rows(session, ctx)


@router.post("/run", response_model=BordereauDetail)
async def run_bordereau(session: SessionDep, ctx: CtxDep, scenario: str) -> BordereauDetail:
    """Dev/ingestion trigger: process one fixture scenario (a premium or claims
    bordereau period context — completeness check, format compliance check,
    reconciliation, data currency, or a proactive timeliness alert)."""
    try:
        return await _service.process(session, ctx, scenario)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/run-completeness-check", response_model=BordereauDetail)
async def run_completeness_check(
    session: SessionDep, ctx: CtxDep, carrier_name: str, reporting_period: str, due_date: str,
) -> BordereauDetail:
    """BR-02 live: a real transaction-universe completeness check built from actual
    Bind & Issuance premium-ledger entries and Triage/Renewal/Endorsement activity —
    not a fixture."""
    return await _service.run_completeness_check(
        session, ctx, carrier_name=carrier_name, reporting_period=reporting_period,
        due_date=due_date)


@router.post("/run-format-check", response_model=BordereauDetail)
async def run_format_compliance_check(
    session: SessionDep, ctx: CtxDep, carrier_name: str, reporting_period: str, due_date: str,
) -> BordereauDetail:
    """BR-03 live: a real format-compliance check against the carrier's actual
    Requirement Profile and real compiled ledger transactions."""
    try:
        return await _service.run_format_compliance_check(
            session, ctx, carrier_name=carrier_name, reporting_period=reporting_period,
            due_date=due_date)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/run-timeliness-check", response_model=BordereauDetail)
async def run_timeliness_check(
    session: SessionDep, ctx: CtxDep, carrier_name: str, reporting_period: str, due_date: str,
) -> BordereauDetail:
    """BR-05 live: a real, carrier-calibrated submission-timeliness alert."""
    try:
        return await _service.run_timeliness_check(
            session, ctx, carrier_name=carrier_name, reporting_period=reporting_period,
            due_date=due_date)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/export-sheet")
async def export_bordereaux_to_sheet(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: exports every bordereau currently in this
    tenant's list — regardless of review status — to the connected spreadsheet.
    Registered before "/{submission_id}" so "export-sheet" is never matched as a
    submission id."""
    status_str = await _service.export_all_to_sheet(session, ctx)
    return {"status": status_str}


@router.post("/export-drive")
async def export_bordereaux_to_drive(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: generates one PDF covering every bordereau
    currently in this tenant's list and uploads it to the connected Drive."""
    status_str = await _service.export_all_to_drive(session, ctx)
    return {"status": status_str}


@router.get("/{submission_id}", response_model=BordereauDetail)
async def get_bordereau(session: SessionDep, ctx: CtxDep, submission_id: str) -> BordereauDetail:
    detail = await _service.get_detail(session, ctx, submission_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bordereau not found")
    return detail


@router.post("/{submission_id}/act")
async def act_on_bordereau(
    session: SessionDep, ctx: CtxDep, submission_id: str, body: ActRequest
) -> dict[str, str]:
    """Human action: approve (mark reviewed) | send (submit to carrier) | escalate."""
    try:
        return await _service.act(session, ctx, submission_id, body.action)
    except AuthorityError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/{submission_id}/add-to-calendar")
async def add_bordereau_to_calendar(
    session: SessionDep, ctx: CtxDep, submission_id: str
) -> dict[str, str]:
    """Manual, per-item: creates/updates one all-day Google Calendar event for
    this one bordereau, dated at its due date."""
    try:
        status_str = await _service.add_to_calendar(session, ctx, submission_id)
        return {"status": status_str}
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
