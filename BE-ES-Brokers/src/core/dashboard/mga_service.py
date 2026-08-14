"""Real, cross-workflow dashboard data for the MGA vertical — every number here is
computed from real rows, never a fixed/example value. Sibling to ``service.py`` (the
ES-vertical dashboard); kept separate because the two verticals' workflow name strings
and result tables don't overlap, not because this is a new workflow of its own.

Every MGA workflow already writes to the shared, vertical-agnostic ``ReviewItem`` /
``OutputPackage`` tables (same pattern ``core/assistant/service.py`` relies on), so the
bulk of this overview is one shared query filtered to the 10 real MGA ``WORKFLOW``
constants. Bound premium and hit ratio aren't derivable from that shared pair alone, so
those two read directly from ``MgaPremiumLedger`` / ``MgaBindResult`` / ``MgaQuotingResult``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.common.dtos import Ctx
from core.common.enums import ReviewStatus
from core.models import OutputPackage, ReviewItem
from verticals.mga.models import MgaBindResult, MgaPremiumLedger, MgaQuotingResult

_RECENT_ACTIVITY_LIMIT = 12
_DAILY_PIPELINE_DAYS = 7

# The 10 real WORKFLOW constants from each verticals/mga/*/service.py, mapped to
# display labels — the MGA-vertical equivalent of core/assistant/service.py's
# WORKFLOW_LABELS (which is ES-only; MGA workflow strings don't appear there).
MGA_WORKFLOW_LABELS: dict[str, str] = {
    "submission-triage": "Submission Triage",
    "renewal-management": "Renewal Management",
    "broker-copilot": "Broker Communication Copilot",
    "endorsement-processing": "Endorsement Processing",
    "quoting-rating": "Quoting & Rating Support",
    "bind-issuance": "Bind Order & Issuance",
    "appetite-governance": "Appetite Governance & Audit Trail",
    "portfolio-reporting": "Portfolio & Book Performance Reporting",
    "bordereau-reporting": "Bordereau Reporting",
    "claims-intake": "Claims Intake Coordination",
}


def _label_for(workflow: str) -> str:
    return MGA_WORKFLOW_LABELS.get(workflow, workflow)


async def _mga_rows(session: AsyncSession, tenant_id: str) -> list[tuple[ReviewItem, OutputPackage]]:
    result = await session.execute(
        select(ReviewItem, OutputPackage)
        .join(OutputPackage, col(ReviewItem.output_package_id) == col(OutputPackage.id))
        .where(
            col(ReviewItem.tenant_id) == tenant_id,
            col(OutputPackage.workflow).in_(MGA_WORKFLOW_LABELS),
        )
        .order_by(col(ReviewItem.created_at).desc())
    )
    return list(result.all())


def _recent_activity_detail(payload: dict[str, Any], ri: ReviewItem) -> str:
    return (
        payload.get("named_insured")
        or payload.get("submission_id")
        or ri.submission_id
        or ri.id
    )


async def build_mga_dashboard_overview(session: AsyncSession, ctx: Ctx) -> dict[str, Any]:
    rows = await _mga_rows(session, ctx.tenant_id)
    today = datetime.now(UTC).date()
    month_start = today.replace(day=1)

    workflow_counts: dict[str, int] = {}
    for ri, op in rows:
        if ri.status == ReviewStatus.PENDING:
            label = _label_for(op.workflow)
            workflow_counts[label] = workflow_counts.get(label, 0) + 1

    submissions_today = sum(
        1 for ri, op in rows
        if op.workflow == "submission-triage" and ri.created_at.date() == today
    )
    quotes_today = sum(
        1 for ri, op in rows
        if op.workflow == "quoting-rating" and ri.created_at.date() == today
    )
    binds_today = sum(
        1 for ri, op in rows
        if op.workflow == "bind-issuance" and ri.created_at.date() == today
    )
    endorsements_pending = workflow_counts.get(_label_for("endorsement-processing"), 0)
    renewals_pending = workflow_counts.get(_label_for("renewal-management"), 0)

    bound_premium_mtd = (
        await session.execute(
            select(func.sum(MgaPremiumLedger.premium)).where(
                col(MgaPremiumLedger.tenant_id) == ctx.tenant_id,
                col(MgaPremiumLedger.created_at) >= datetime.combine(month_start, datetime.min.time(), tzinfo=UTC),
            )
        )
    ).scalar() or 0.0

    bound_count_period = (
        await session.execute(
            select(func.count()).select_from(MgaBindResult).where(
                col(MgaBindResult.tenant_id) == ctx.tenant_id,
                col(MgaBindResult.status) == "BOUND",
                col(MgaBindResult.created_at) >= datetime.combine(month_start, datetime.min.time(), tzinfo=UTC),
            )
        )
    ).scalar() or 0
    quoted_count_period = (
        await session.execute(
            select(func.count()).select_from(MgaQuotingResult).where(
                col(MgaQuotingResult.tenant_id) == ctx.tenant_id,
                col(MgaQuotingResult.created_at) >= datetime.combine(month_start, datetime.min.time(), tzinfo=UTC),
            )
        )
    ).scalar() or 0
    hit_ratio_pct = (
        round((bound_count_period / quoted_count_period) * 100, 1)
        if quoted_count_period > 0 else None
    )

    recent_activity = [
        {
            "workflow": _label_for(op.workflow),
            "ref": _recent_activity_detail(op.payload or {}, ri),
            "status": ri.status.value,
            "created_at": ri.created_at.isoformat(),
        }
        for ri, op in rows[:_RECENT_ACTIVITY_LIMIT]
    ]

    # Real counts over the last 7 real days — not a fabricated multi-month trend;
    # same honest-data convention as the ES dashboard service.
    daily_pipeline = []
    for i in range(_DAILY_PIPELINE_DAYS - 1, -1, -1):
        day = today - timedelta(days=i)
        subs = sum(
            1 for ri, op in rows
            if op.workflow == "submission-triage" and ri.created_at.date() == day
        )
        bound = sum(
            1 for ri, op in rows
            if op.workflow == "bind-issuance" and ri.created_at.date() == day
        )
        daily_pipeline.append({"date": day.isoformat(), "submissions": subs, "bound": bound})

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_counts": workflow_counts,
        "submissions_today": submissions_today,
        "quotes_today": quotes_today,
        "binds_today": binds_today,
        "endorsements_pending": endorsements_pending,
        "renewals_pending": renewals_pending,
        "bound_premium_mtd": float(bound_premium_mtd),
        "hit_ratio_pct": hit_ratio_pct,
        "recent_activity": recent_activity,
        "daily_pipeline": daily_pipeline,
    }
