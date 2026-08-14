"""Portfolio & Book Performance Reporting pipeline — ingest(dataset fixture, or eventually
a live pull from the result tables of Submission Triage, Quoting & Rating, Bind Order &
Issuance, Renewal Management, and Appetite Governance) -> analyze (PBR-01..07) -> review
-> audit. Like Appetite Governance & Audit Trail, this workflow makes no underwriting
decisions of its own — it aggregates and presents; every report routes to a
human-reviewed queue before being sent externally.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.audit import DefaultAuditService
from core.common.dtos import AuditEntry, Ctx, Draft
from core.common.dtos import Decision as DecisionDTO
from core.common.dtos import OutputPackage as OutputPackageDTO
from core.common.enums import DecisionOutcome, ReviewAction
from core.config import get_settings
from core.ingestion import (
    build_connector_service,
    resolve_drive_folder_id,
    resolve_sheet_id,
    try_append_rows,
    try_put_file,
)
from core.ingestion.pdf_export import render_bulk_summary_pdf
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.models import Submission
from core.review_queue import DefaultReviewQueueService
from verticals.mga.models import MgaPortfolioResult
from verticals.mga.portfolio_reporting.engine import PortfolioAnalysis, PortfolioEngine
from verticals.mga.portfolio_reporting.fixtures import load_scenario
from verticals.mga.portfolio_reporting.live_aggregator import (
    build_appetite_exposure_request,
    build_data_completeness_request,
    build_full_book_report_request,
    build_segment_loss_ratio_request,
)
from verticals.mga.portfolio_reporting.schema import (
    ActivityEntry,
    AppetiteExposureSectionOut,
    BrokerProductionOut,
    DataCompletenessOut,
    FunnelStageOut,
    GapOut,
    LossRatioOut,
    PortfolioReportDetail,
    PortfolioReportRow,
    RenewalRetentionOut,
)

WORKFLOW = "portfolio-reporting"
_SHEET_TAB = "Portfolio & Book"
_SHEET_HEADER = ["ID", "Period", "Status"]

_ACTIONS = {
    "approve": ReviewAction.APPROVE,
    "send": ReviewAction.SEND,       # human-triggered external report send
    "escalate": ReviewAction.ESCALATE,
}


class PortfolioService:
    def __init__(self) -> None:
        self.engine = PortfolioEngine()
        self.review_queue = DefaultReviewQueueService()
        self.audit = DefaultAuditService()

    async def process(
        self, session: AsyncSession, ctx: Ctx, scenario: str,
        request_override: dict[str, Any] | None = None,
    ) -> PortfolioReportDetail:
        request = request_override or load_scenario(scenario)
        if request is None:
            raise KeyError(f"no portfolio-reporting fixture '{scenario}' for Workflow-08")

        sub = Submission(tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                         external_ref=scenario, subject=request.get("period", scenario),
                         status="portfolio-reporting")
        session.add(sub)
        await session.flush()

        analysis = self.engine.analyze(request)
        detail = self._build_detail(sub.id, scenario, analysis)

        session.add(MgaPortfolioResult(
            tenant_id=ctx.tenant_id, submission_id=sub.id, status=analysis.status,
            completeness_status=analysis.completeness_status, gap_count=len(analysis.gaps),
            has_loss_ratio=analysis.loss_ratio is not None,
            has_renewal_retention=analysis.renewal_retention is not None,
            has_appetite_exposure=analysis.appetite_exposure is not None))

        out_dto = OutputPackageDTO(
            submission_id=sub.id,
            decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None,
                                 rationale=analysis.rationale),
            draft=Draft(text=analysis.rationale, citations=[]),
            flags=[analysis.status], missing_info=[],
            payload={"detail": detail.model_dump(by_alias=True)})
        await self.review_queue.enqueue(session, ctx, out_dto, WORKFLOW)

        await self.audit.record(session, ctx, AuditEntry(
            actor="ai", who="system", what=f"Portfolio report evaluated: {analysis.status}",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"scenario": scenario, "status": analysis.status}))
        await session.commit()
        return detail

    async def run_full_book_report(
        self, session: AsyncSession, ctx: Ctx, *, period: str,
    ) -> PortfolioReportDetail:
        """PBR-01/02 live: real submitted/quoted/bound counts and real earned premium
        from Triage/Quoting/Bind's own persisted output — not a fixture. PBR-04
        (renewal retention) is reported as an honest 0/0 within this report; see
        live_aggregator.py for why no live retention signal exists to read yet."""
        request = await build_full_book_report_request(session, ctx, period=period)
        return await self.process(session, ctx, f"live-full-book-{period}", request_override=request)

    async def run_segment_loss_ratio(
        self, session: AsyncSession, ctx: Ctx, *, class_code: str, period: str,
    ) -> PortfolioReportDetail:
        """PBR-02/03 live: real bound-account count and earned premium for one class
        code, from MgaPremiumLedger — not a fixture."""
        request = await build_segment_loss_ratio_request(
            session, ctx, class_code=class_code, period=period)
        return await self.process(
            session, ctx, f"live-segment-{class_code}-{period}", request_override=request)

    async def run_data_completeness(
        self, session: AsyncSession, ctx: Ctx, *, period: str,
    ) -> PortfolioReportDetail:
        """PBR-05 live: real per-source-workflow activity counts — not a fixture."""
        request = await build_data_completeness_request(session, ctx, period=period)
        return await self.process(session, ctx, f"live-completeness-{period}", request_override=request)

    async def run_appetite_exposure(
        self, session: AsyncSession, ctx: Ctx, *, period: str,
    ) -> PortfolioReportDetail:
        """PBR-07 live: the most recent real AG-06 finding Appetite Governance has
        actually produced, pulled through verbatim — not a fixture."""
        request = await build_appetite_exposure_request(session, ctx, period=period)
        if request is None:
            raise KeyError(
                "Appetite Governance has no live portfolio-concentration (AG-06) "
                "finding on record yet — nothing to pull through")
        return await self.process(session, ctx, f"live-exposure-{period}", request_override=request)

    def _build_detail(
        self, sub_id: str, scenario: str, analysis: PortfolioAnalysis,
    ) -> PortfolioReportDetail:
        now = datetime.now(UTC).isoformat()

        return PortfolioReportDetail(
            reportId=f"PBR-{sub_id[-6:]}",
            period=analysis.period,
            dataCompleteness=DataCompletenessOut(
                status=analysis.completeness_status,
                gaps=[GapOut(sourceWorkflow=g.source_workflow, dateRange=g.date_range,
                             reason=g.reason,
                             crossReferencedFindingId=g.cross_referenced_finding_id)
                     for g in analysis.gaps]),
            funnel=[FunnelStageOut(stage=f.stage, count=f.count,
                                   pctOfPriorStage=f.pct_of_prior_stage)
                   for f in analysis.funnel],
            lossRatio=(
                LossRatioOut(
                    periodBasis=analysis.loss_ratio.period_basis,
                    earnedPremium=analysis.loss_ratio.earned_premium,
                    incurredLosses=analysis.loss_ratio.incurred_losses,
                    ratioPct=analysis.loss_ratio.ratio_pct,
                    lowVolumeFlag=analysis.loss_ratio.low_volume_flag,
                    singleEventDrivenFlag=analysis.loss_ratio.single_event_driven_flag,
                    detail=analysis.loss_ratio.detail)
                if analysis.loss_ratio is not None else None),
            renewalRetention=(
                RenewalRetentionOut(
                    eligible=analysis.renewal_retention.eligible,
                    retained=analysis.renewal_retention.retained,
                    nonRenewedUnderwritingDecision=(
                        analysis.renewal_retention.non_renewed_underwriting_decision),
                    lapsedNoDecision=analysis.renewal_retention.lapsed_no_decision,
                    retentionRatePct=analysis.renewal_retention.retention_rate_pct,
                    lineItems=analysis.renewal_retention.line_items)
                if analysis.renewal_retention is not None else None),
            brokerProduction=[
                BrokerProductionOut(
                    brokerAgency=b.broker_agency,
                    currentPeriodPremium=b.current_period_premium,
                    priorPeriodPremium=b.prior_period_premium, pctChange=b.pct_change,
                    significantDecline=b.significant_decline, detail=b.detail)
                for b in analysis.broker_production
            ],
            appetiteExposureSection=(
                AppetiteExposureSectionOut(
                    pulledFrom=analysis.appetite_exposure.pulled_from,
                    findingId=analysis.appetite_exposure.finding_id,
                    summary=analysis.appetite_exposure.summary,
                    lowVolumeFlag=analysis.appetite_exposure.low_volume_flag)
                if analysis.appetite_exposure is not None else None),
            status=analysis.status,
            rationale=analysis.rationale,
            activity=[ActivityEntry(at=now, who="system (AI)",
                                    what=f"Portfolio report evaluated -> {analysis.status}",
                                    ctx=scenario)],
        )

    # ── list / detail / act ──
    async def list_rows(self, session: AsyncSession, ctx: Ctx) -> list[PortfolioReportRow]:
        stmt = (select(ReviewItemRow, OutputPackageRow)
                .join(OutputPackageRow,
                      col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
                .where(col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                       col(ReviewItemRow.workflow) == WORKFLOW))
        rows: list[PortfolioReportRow] = []
        for _item, pkg in (await session.execute(stmt)).all():
            payload = pkg.payload or {}
            if "detail" not in payload:
                continue
            d = PortfolioReportDetail.model_validate(payload["detail"])
            rows.append(PortfolioReportRow(id=pkg.submission_id, period=d.period,
                                           status=d.status))
        return rows

    async def get_detail(
        self, session: AsyncSession, ctx: Ctx, submission_id: str
    ) -> PortfolioReportDetail | None:
        pkg = (await session.execute(
            select(OutputPackageRow).where(
                col(OutputPackageRow.tenant_id) == ctx.tenant_id,
                col(OutputPackageRow.submission_id) == submission_id,
                col(OutputPackageRow.workflow) == WORKFLOW))
        ).scalars().first()
        if pkg is None or not pkg.payload:
            return None
        item = (await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                col(ReviewItemRow.submission_id) == submission_id,
                col(ReviewItemRow.workflow) == WORKFLOW))
        ).scalars().first()
        review_status = (
            item.status.value if item is not None and hasattr(item.status, "value")
            else str(item.status) if item is not None else None)
        detail_payload = {**pkg.payload["detail"], "reviewStatus": review_status}
        return PortfolioReportDetail.model_validate(detail_payload)

    async def act(
        self, session: AsyncSession, ctx: Ctx, submission_id: str, action: str,
    ) -> dict[str, str]:
        review_action = _ACTIONS.get(action)
        if review_action is None:
            raise ValueError(f"unknown action '{action}'; allowed: {sorted(_ACTIONS)}")
        item = (await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                col(ReviewItemRow.submission_id) == submission_id,
                col(ReviewItemRow.workflow) == WORKFLOW))
        ).scalars().first()
        if item is None:
            raise KeyError(f"no portfolio-reporting review item for submission '{submission_id}'")
        result = await self.review_queue.act(session, ctx, item.id, review_action)
        await self.audit.record(session, ctx, AuditEntry(
            actor="human", who=ctx.user_id, what=f"{action} (role={ctx.role.value})",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"submission": submission_id, "action": action}))
        await session.commit()
        return {"id": result.id, "status": result.status.value}

    async def export_all_to_sheet(self, session: AsyncSession, ctx: Ctx) -> str:
        """Exports every portfolio report currently in this tenant's list —
        regardless of review status — as one row each into the shared
        spreadsheet's "Portfolio & Book" tab. Manual, button-triggered; never
        fails the caller."""
        sheet_id = await resolve_sheet_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        sheet_rows = [[r.id, r.period, r.status] for r in rows]
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_append_rows(
            connector, ctx, sheet_id, sheet_rows, tab=_SHEET_TAB, header=_SHEET_HEADER
        )

    async def export_all_to_drive(self, session: AsyncSession, ctx: Ctx) -> str:
        """Generates one PDF (one page per portfolio report currently in this
        tenant's list, regardless of review status) and uploads it to the
        tenant's connected Drive. Manual, button-triggered."""
        folder_id = await resolve_drive_folder_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        pdf_rows = [
            [("ID", r.id), ("Period", r.period), ("Status", r.status)]
            for r in rows
        ]
        pdf_bytes = render_bulk_summary_pdf("Portfolio & Book", pdf_rows)
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        return await try_put_file(
            connector, ctx, folder_id, f"portfolio-reporting-{timestamp}.pdf",
            pdf_bytes, "application/pdf",
        )
