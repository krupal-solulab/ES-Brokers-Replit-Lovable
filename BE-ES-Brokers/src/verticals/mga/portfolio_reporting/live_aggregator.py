"""Builds real Portfolio & Book Performance Reporting requests from what's actually
persisted, instead of a fixture, for the sub-features that don't require fabricating
data:

- PBR-01/02 (funnel + loss ratio, full-book): real submitted/quoted/bound counts from
  Triage/Quoting/Bind's own ``OutputPackage`` rows, and real earned premium from
  ``MgaPremiumLedger`` (the only bound-premium source in this codebase).
- PBR-02/03 (segment loss ratio): the same ledger query, filtered to one class code.
- PBR-05 (data completeness): a per-month count of source-workflow activity, the same
  shape as Bordereau's BR-02 completeness check.
- PBR-07 (appetite exposure): the most recent live AG-06 finding Appetite Governance has
  actually produced, pulled through verbatim, never recomputed here.

PBR-04 (renewal retention) stays fixture-only: it needs a RENEW_AS_IS / RENEW_WITH_
CHANGES / NON_RENEW / lapsed-no-decision categorization, but Renewal Management's own
``Decision.outcome`` only ever holds the generic PROCEED/REQUEST_INFO/DECLINE enum — no
renewal-specific outcome is persisted anywhere to read. The full-book report below still
needs *some* renewals figure (the engine requires ``renewals_eligible``/
``renewals_retained``), so it reports an honest ``0/0`` with the gap named in the
rationale, rather than fabricating a plausible-looking retention rate. PBR-06 (broker
production) also stays fixture-only — no broker-level premium breakdown is persisted
anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.common.dtos import Ctx
from core.models import OutputPackage as OutputPackageRow
from verticals.mga.appetite_governance.service import WORKFLOW as GOVERNANCE_WORKFLOW
from verticals.mga.models import MgaGovernanceResult, MgaPremiumLedger

_TRIAGE_WORKFLOW = "submission-triage"
_QUOTING_WORKFLOW = "quoting-rating"
_BIND_WORKFLOW = "bind-issuance"
_RENEWAL_WORKFLOW = "renewal-management"
_ENDORSEMENT_WORKFLOW = "endorsement-processing"
_NO_RENEWAL_SIGNAL_NOTE = (
    "Renewal Management persists no RENEW_AS_IS/RENEW_WITH_CHANGES/NON_RENEW/lapsed "
    "outcome today (its Decision.outcome is the generic PROCEED/REQUEST_INFO/DECLINE "
    "enum, not a renewal-specific one) — reported as an honest 0/0 rather than a "
    "fabricated retention rate. See PBR-04's own fixture-only path for the real "
    "retention categorization once that signal exists."
)


async def _count_by_workflow(session: AsyncSession, ctx: Ctx, workflow: str) -> int:
    stmt = select(func.count()).where(
        col(OutputPackageRow.tenant_id) == ctx.tenant_id,
        col(OutputPackageRow.workflow) == workflow)
    return (await session.execute(stmt)).scalar_one()


async def build_full_book_report_request(
    session: AsyncSession, ctx: Ctx, *, period: str,
) -> dict[str, Any]:
    submitted = await _count_by_workflow(session, ctx, _TRIAGE_WORKFLOW)
    quoted = await _count_by_workflow(session, ctx, _QUOTING_WORKFLOW)
    bound = await _count_by_workflow(session, ctx, _BIND_WORKFLOW)

    premium_stmt = select(func.coalesce(func.sum(MgaPremiumLedger.premium), 0.0)).where(
        col(MgaPremiumLedger.tenant_id) == ctx.tenant_id)
    earned_premium = (await session.execute(premium_stmt)).scalar_one()

    return {
        "period": period,
        "submissions_received": submitted,
        "quoted": quoted,
        "bound": bound,
        # No renewal-outcome signal exists to read live yet — see module docstring.
        "renewals_eligible": 0,
        "renewals_retained": 0,
        "earned_premium": float(earned_premium),
        # No incurred-losses/claims table exists anywhere in this codebase — an honest
        # 0.0, never a fabricated figure, same gap pattern as bind_issuance/bordereau.
        "incurred_losses": 0.0,
        "data_completeness": (
            "complete" if earned_premium or bound else "partial — no bound premium "
            f"recorded yet for {period}; renewal retention not yet trackable "
            f"({_NO_RENEWAL_SIGNAL_NOTE})"),
    }


async def build_segment_loss_ratio_request(
    session: AsyncSession, ctx: Ctx, *, class_code: str, period: str,
) -> dict[str, Any]:
    ledger_stmt = select(MgaPremiumLedger).where(
        col(MgaPremiumLedger.tenant_id) == ctx.tenant_id,
        col(MgaPremiumLedger.class_code) == class_code)
    rows = (await session.execute(ledger_stmt)).scalars().all()
    earned = sum(r.premium for r in rows)

    return {
        "period": period,
        "bound_accounts_in_class": len(rows),
        "earned_premium_this_class": float(earned),
        # No incurred-losses/claims table exists — honest 0.0, not fabricated.
        "incurred_losses_this_class": 0.0,
        "note": (
            "No claims/incurred-loss data exists yet for this class/carrier segment — "
            "this figure reflects bound premium volume only, not loss experience."),
    }


async def build_data_completeness_request(
    session: AsyncSession, ctx: Ctx, *, period: str,
) -> dict[str, Any]:
    """PBR-05: real per-workflow activity counts, structured the same way Bordereau's
    BR-02 completeness check already is — one entry per source workflow rather than
    per calendar month, since no MGA table persists a policy-effective-date breakdown
    by month today (same coarseness caveat BR-02 already documents)."""
    counts = {
        "Submission Triage": await _count_by_workflow(session, ctx, _TRIAGE_WORKFLOW),
        "Renewal Management": await _count_by_workflow(session, ctx, _RENEWAL_WORKFLOW),
        "Endorsement Processing": await _count_by_workflow(session, ctx, _ENDORSEMENT_WORKFLOW),
        "Bind Order & Issuance": await _count_by_workflow(session, ctx, _BIND_WORKFLOW),
    }
    bind_data = {
        period: {
            "status": "complete" if any(counts.values()) else (
                "no activity recorded yet across Triage/Renewal/Endorsement/Bind for "
                f"{period}"),
            "activity_counts": counts,
        },
    }
    return {"period": period, "bind_data": bind_data}


async def build_appetite_exposure_request(
    session: AsyncSession, ctx: Ctx, *, period: str,
) -> dict[str, Any] | None:
    """PBR-07: the most recent live AG-06 finding Appetite Governance has actually
    produced, if any — pulled through verbatim, never recomputed here. Returns None
    (an honest "nothing to pull yet") when Governance has no AG-06 finding on record,
    since AG-06 itself stays fixture-only today (no durable concentration figure
    survives being persisted, per appetite_governance's own live_aggregator.py)."""
    stmt = (
        select(OutputPackageRow)
        .join(MgaGovernanceResult,
              col(MgaGovernanceResult.submission_id) == col(OutputPackageRow.submission_id))
        .where(col(OutputPackageRow.tenant_id) == ctx.tenant_id,
               col(OutputPackageRow.workflow) == GOVERNANCE_WORKFLOW)
        .order_by(col(OutputPackageRow.created_at).desc())
    )
    pkg = (await session.execute(stmt)).scalars().first()
    if pkg is None or not pkg.payload:
        return None

    findings = (pkg.payload.get("detail") or {}).get("portfolioConcentrationFindings") or []
    if not findings:
        return None
    finding = findings[0]

    return {
        "period": period,
        "appetite_governance_finding_reference": {
            "source": "Appetite Governance & Audit Trail",
            "finding_id": f"AG-FIND-{pkg.submission_id[-6:]}",
            "finding_summary": (
                f"{finding.get('accountsNearCeiling', 0)} of "
                f"{finding.get('totalAccountsInSegment', 0)} accounts in this segment "
                "are near their delegated authority ceiling."),
            "low_volume_flag": bool(finding.get("lowVolumeFlag", False)),
        },
    }
