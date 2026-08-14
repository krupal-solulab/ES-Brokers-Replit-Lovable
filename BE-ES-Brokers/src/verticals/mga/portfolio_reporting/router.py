"""Routes under /api/mga/portfolio-reporting — list, detail, run (generate a report),
act. Like Appetite Governance & Audit Trail, this workflow makes no underwriting
decisions; every report routes to a human-reviewed queue before being sent externally."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.db import get_session
from core.review_queue import AuthorityError
from core.tenancy import get_ctx
from verticals.mga.portfolio_reporting.schema import (
    ActRequest,
    PortfolioReportDetail,
    PortfolioReportRow,
)
from verticals.mga.portfolio_reporting.service import PortfolioService

router = APIRouter(prefix="/portfolio-reporting", tags=["mga:portfolio-reporting"])
_service = PortfolioService()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CtxDep = Annotated[Ctx, Depends(get_ctx)]


@router.get("", response_model=list[PortfolioReportRow])
async def list_reports(session: SessionDep, ctx: CtxDep) -> list[PortfolioReportRow]:
    return await _service.list_rows(session, ctx)


@router.post("/run", response_model=PortfolioReportDetail)
async def run_report(session: SessionDep, ctx: CtxDep, scenario: str) -> PortfolioReportDetail:
    """Dev/ingestion trigger: process one fixture scenario (a full-book period, a
    class/carrier loss-ratio segment, renewal outcomes, a bind-data completeness check,
    broker production figures, or an appetite exposure finding reference)."""
    try:
        return await _service.process(session, ctx, scenario)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/run-full-book-report", response_model=PortfolioReportDetail)
async def run_full_book_report(
    session: SessionDep, ctx: CtxDep, period: str,
) -> PortfolioReportDetail:
    """PBR-01/02 live: a real full-book report built from actual Triage/Quoting/Bind
    output and MgaPremiumLedger — not a fixture."""
    return await _service.run_full_book_report(session, ctx, period=period)


@router.post("/run-segment-loss-ratio", response_model=PortfolioReportDetail)
async def run_segment_loss_ratio(
    session: SessionDep, ctx: CtxDep, class_code: str, period: str,
) -> PortfolioReportDetail:
    """PBR-02/03 live: a real class/carrier segment loss ratio built from actual
    MgaPremiumLedger rows — not a fixture."""
    return await _service.run_segment_loss_ratio(session, ctx, class_code=class_code, period=period)


@router.post("/run-data-completeness", response_model=PortfolioReportDetail)
async def run_data_completeness(session: SessionDep, ctx: CtxDep, period: str) -> PortfolioReportDetail:
    """PBR-05 live: a real per-source-workflow activity completeness check — not a
    fixture."""
    return await _service.run_data_completeness(session, ctx, period=period)


@router.post("/run-appetite-exposure", response_model=PortfolioReportDetail)
async def run_appetite_exposure(session: SessionDep, ctx: CtxDep, period: str) -> PortfolioReportDetail:
    """PBR-07 live: the most recent real AG-06 finding Appetite Governance has
    actually produced, pulled through verbatim — not a fixture."""
    try:
        return await _service.run_appetite_exposure(session, ctx, period=period)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/export-sheet")
async def export_reports_to_sheet(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: exports every portfolio report currently in
    this tenant's list — regardless of review status — to the connected
    spreadsheet. Registered before "/{submission_id}" so "export-sheet" is
    never matched as a submission id."""
    status_str = await _service.export_all_to_sheet(session, ctx)
    return {"status": status_str}


@router.post("/export-drive")
async def export_reports_to_drive(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: generates one PDF covering every portfolio
    report currently in this tenant's list and uploads it to the connected
    Drive."""
    status_str = await _service.export_all_to_drive(session, ctx)
    return {"status": status_str}


@router.get("/{submission_id}", response_model=PortfolioReportDetail)
async def get_report(session: SessionDep, ctx: CtxDep, submission_id: str) -> PortfolioReportDetail:
    detail = await _service.get_detail(session, ctx, submission_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "portfolio report not found")
    return detail


@router.post("/{submission_id}/act")
async def act_on_report(
    session: SessionDep, ctx: CtxDep, submission_id: str, body: ActRequest
) -> dict[str, str]:
    """Human action: approve (mark reviewed) | send (submit report externally) |
    escalate."""
    try:
        return await _service.act(session, ctx, submission_id, body.action)
    except AuthorityError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
