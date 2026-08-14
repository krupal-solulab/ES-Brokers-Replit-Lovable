"""Routes under /api/mga/appetite-governance — list, detail, run (process an audit
period), act. This workflow makes no underwriting decisions; every finding routes to a
human-reviewed governance suggestion queue, never an automated action."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.db import get_session
from core.review_queue import AuthorityError
from core.tenancy import get_ctx
from verticals.mga.appetite_governance.schema import ActRequest, GovernanceDetail, GovernanceRow
from verticals.mga.appetite_governance.service import GovernanceService

router = APIRouter(prefix="/appetite-governance", tags=["mga:appetite-governance"])
_service = GovernanceService()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CtxDep = Annotated[Ctx, Depends(get_ctx)]


@router.get("", response_model=list[GovernanceRow])
async def list_audits(session: SessionDep, ctx: CtxDep) -> list[GovernanceRow]:
    return await _service.list_rows(session, ctx)


@router.post("/run", response_model=GovernanceDetail)
async def run_audit(session: SessionDep, ctx: CtxDep, scenario: str) -> GovernanceDetail:
    """Dev/ingestion trigger: process one fixture scenario (an audit period, a rule
    version change, override events, an external audit request, or a portfolio
    concentration snapshot)."""
    try:
        return await _service.process(session, ctx, scenario)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/run-audit-report", response_model=GovernanceDetail)
async def run_audit_report(
    session: SessionDep, ctx: CtxDep, carrier_name: str, period: str, requested_by: str,
) -> GovernanceDetail:
    """AG-05 live: a real CARRIER_DELEGATED_AUTHORITY_AUDIT built from actual logged
    decision counts across Triage/Renewal/Bind/Endorsement and real ceiling-breach
    referrals — not a fixture."""
    return await _service.run_audit_report(
        session, ctx, carrier_name=carrier_name, period=period, requested_by=requested_by)


@router.post("/run-decision-trail", response_model=GovernanceDetail)
async def run_decision_trail(session: SessionDep, ctx: CtxDep, period: str) -> GovernanceDetail:
    """AG-02 live: a real decision trail built from actual Triage/Renewal Decision +
    AuditEntry rows — who decided what, citing which rules version."""
    return await _service.run_decision_trail(session, ctx, period=period)


@router.post("/run-override-patterns", response_model=GovernanceDetail)
async def run_override_patterns(session: SessionDep, ctx: CtxDep, period: str) -> GovernanceDetail:
    """AG-04 live: real override events inferred from a human approve action following
    an AI DECLINE/REQUEST_INFO decision — see live_aggregator.py for why this is the
    honest proxy for "override" in this codebase's real action model."""
    return await _service.run_override_patterns(session, ctx, period=period)


@router.post("/export-sheet")
async def export_audits_to_sheet(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: exports every governance report currently in
    this tenant's list — regardless of review status — to the connected
    spreadsheet. Registered before "/{submission_id}" so "export-sheet" is
    never matched as a submission id."""
    status_str = await _service.export_all_to_sheet(session, ctx)
    return {"status": status_str}


@router.post("/export-drive")
async def export_audits_to_drive(session: SessionDep, ctx: CtxDep) -> dict[str, str]:
    """Manual, button-triggered: generates one PDF covering every governance
    report currently in this tenant's list and uploads it to the connected
    Drive."""
    status_str = await _service.export_all_to_drive(session, ctx)
    return {"status": status_str}


@router.get("/{submission_id}", response_model=GovernanceDetail)
async def get_audit(session: SessionDep, ctx: CtxDep, submission_id: str) -> GovernanceDetail:
    detail = await _service.get_detail(session, ctx, submission_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "governance analysis not found")
    return detail


@router.post("/{submission_id}/act")
async def act_on_audit(
    session: SessionDep, ctx: CtxDep, submission_id: str, body: ActRequest
) -> dict[str, str]:
    """Human action: approve (mark reviewed) | send (submit audit report externally) |
    escalate."""
    try:
        return await _service.act(session, ctx, submission_id, body.action)
    except AuthorityError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
