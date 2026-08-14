"""Bordereau Reporting pipeline — ingest(dataset fixture, or eventually a live pull
from the underwriting system of record: Submission Triage, Renewal Management,
Endorsement Processing) -> analyze (BR-02..06) -> review -> audit. A bordereau is a
formal periodic filing under a contractual obligation to a carrier partner — every
compiled bordereau routes to a human-reviewed queue and is never auto-submitted, per
the PRD's permanent human-approval boundary.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
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
    try_create_event,
    try_put_file,
)
from core.ingestion.pdf_export import render_bulk_summary_pdf
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.models import Submission
from core.review_queue import DefaultReviewQueueService
from verticals.mga.bordereau_reporting.engine import BordereauAnalysis, BordereauEngine
from verticals.mga.bordereau_reporting.fixtures import load_scenario
from verticals.mga.bordereau_reporting.live_aggregator import (
    build_completeness_request,
    build_format_compliance_request,
    build_timeliness_request,
)
from verticals.mga.bordereau_reporting.schema import (
    ActivityEntry,
    BordereauDetail,
    BordereauRow,
    CompletenessCheckOut,
    DataCurrencyCheckOut,
    FormatComplianceCheckOut,
    ReconciliationCheckOut,
    TimelinessCheckOut,
)
from verticals.mga.models import MgaBordereauResult

WORKFLOW = "bordereau-reporting"
_SHEET_TAB = "Bordereau Reporting"
_SHEET_HEADER = ["Bordereau ID", "Carrier Name", "Reporting Period", "Status"]

_ACTIONS = {
    "approve": ReviewAction.APPROVE,
    "send": ReviewAction.SEND,       # human-triggered external carrier submission
    "escalate": ReviewAction.ESCALATE,
}


class BordereauService:
    def __init__(self) -> None:
        self.engine = BordereauEngine()
        self.review_queue = DefaultReviewQueueService()
        self.audit = DefaultAuditService()

    async def process(
        self, session: AsyncSession, ctx: Ctx, scenario: str,
        request_override: dict[str, Any] | None = None,
    ) -> BordereauDetail:
        request = request_override or load_scenario(scenario)
        if request is None:
            raise KeyError(f"no bordereau-reporting fixture '{scenario}' for Workflow-09")

        sub = Submission(
            tenant_id=ctx.tenant_id, vertical=ctx.vertical, external_ref=scenario,
            subject=str(request.get("carrier_name", scenario)), status="bordereau-reporting")
        session.add(sub)
        await session.flush()

        analysis = self.engine.analyze(request)
        detail = self._build_detail(sub.id, scenario, analysis)

        session.add(MgaBordereauResult(
            tenant_id=ctx.tenant_id, submission_id=sub.id, status=analysis.status,
            bordereau_type=analysis.bordereau_type,
            completeness_status=analysis.completeness_check.status,
            format_compliance_status=analysis.format_compliance_check.status,
            reconciliation_status=analysis.reconciliation_check.status,
            data_currency_status=analysis.data_currency_check.status))

        out_dto = OutputPackageDTO(
            submission_id=sub.id,
            decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None,
                                 rationale=analysis.rationale),
            draft=Draft(text=analysis.rationale, citations=[]),
            flags=[analysis.status], missing_info=[],
            payload={"detail": detail.model_dump(by_alias=True)})
        await self.review_queue.enqueue(session, ctx, out_dto, WORKFLOW)

        await self.audit.record(session, ctx, AuditEntry(
            actor="ai", who="system", what=f"Bordereau compiled: {analysis.status}",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"scenario": scenario, "status": analysis.status}))
        await session.commit()
        return detail

    async def run_completeness_check(
        self, session: AsyncSession, ctx: Ctx, *, carrier_name: str, reporting_period: str,
        due_date: str,
    ) -> BordereauDetail:
        """BR-02 live: a real transaction-universe completeness check built from actual
        Bind & Issuance ledger entries and Triage/Renewal/Endorsement activity counts —
        not a fixture. See live_aggregator.py for why BR-01/03/04/05/06 have no live
        path yet."""
        request = await build_completeness_request(
            session, ctx, carrier_name=carrier_name, reporting_period=reporting_period,
            due_date=due_date)
        label = f"live-completeness-{carrier_name}-{reporting_period}"
        return await self.process(session, ctx, label, request_override=request)

    async def run_format_compliance_check(
        self, session: AsyncSession, ctx: Ctx, *, carrier_name: str, reporting_period: str,
        due_date: str,
    ) -> BordereauDetail:
        """BR-03 live: a real format-compliance check against the carrier's actual
        MgaCarrierProfile and real ledger transactions."""
        request = await build_format_compliance_request(
            session, ctx, carrier_name=carrier_name, reporting_period=reporting_period,
            due_date=due_date)
        label = f"live-format-{carrier_name}-{reporting_period}"
        return await self.process(session, ctx, label, request_override=request)

    async def run_timeliness_check(
        self, session: AsyncSession, ctx: Ctx, *, carrier_name: str, reporting_period: str,
        due_date: str,
    ) -> BordereauDetail:
        """BR-05 live: a real, carrier-calibrated submission-timeliness alert."""
        request = await build_timeliness_request(
            session, ctx, carrier_name=carrier_name, reporting_period=reporting_period,
            due_date=due_date)
        label = f"live-timeliness-{carrier_name}-{reporting_period}"
        return await self.process(session, ctx, label, request_override=request)

    def _build_detail(
        self, sub_id: str, scenario: str, analysis: BordereauAnalysis,
    ) -> BordereauDetail:
        now = datetime.now(UTC).isoformat()

        return BordereauDetail(
            bordereauId=f"BR-{sub_id[-6:]}",
            bordereauType=analysis.bordereau_type,
            carrierName=analysis.carrier_name,
            reportingPeriod=analysis.reporting_period,
            dueDate=analysis.due_date,
            completenessCheck=CompletenessCheckOut(
                status=analysis.completeness_check.status,
                missingTransactions=analysis.completeness_check.missing_transactions),
            formatComplianceCheck=FormatComplianceCheckOut(
                status=analysis.format_compliance_check.status,
                issues=analysis.format_compliance_check.issues),
            reconciliationCheck=ReconciliationCheckOut(
                status=analysis.reconciliation_check.status,
                discrepancyDetail=analysis.reconciliation_check.discrepancy_detail),
            dataCurrencyCheck=DataCurrencyCheckOut(
                status=analysis.data_currency_check.status,
                staleItems=analysis.data_currency_check.stale_items),
            timelinessCheck=(
                TimelinessCheckOut(
                    daysRemaining=analysis.timeliness_check.days_remaining,
                    compilationTimeNeededDays=(
                        analysis.timeliness_check.compilation_time_needed_days),
                    urgent=analysis.timeliness_check.urgent,
                    detail=analysis.timeliness_check.detail)
                if analysis.timeliness_check is not None else None),
            status=analysis.status,
            rationale=analysis.rationale,
            activity=[ActivityEntry(at=now, who="system (AI)",
                                    what=f"Bordereau compiled -> {analysis.status}",
                                    ctx=scenario)],
        )

    # ── list / detail / act ──
    async def list_rows(self, session: AsyncSession, ctx: Ctx) -> list[BordereauRow]:
        stmt = (select(ReviewItemRow, OutputPackageRow)
                .join(OutputPackageRow,
                      col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
                .where(col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                       col(ReviewItemRow.workflow) == WORKFLOW))
        rows: list[BordereauRow] = []
        for _item, pkg in (await session.execute(stmt)).all():
            payload = pkg.payload or {}
            if "detail" not in payload:
                continue
            d = BordereauDetail.model_validate(payload["detail"])
            rows.append(BordereauRow(id=pkg.submission_id, carrierName=d.carrierName,
                                     reportingPeriod=d.reportingPeriod, status=d.status))
        return rows

    async def get_detail(
        self, session: AsyncSession, ctx: Ctx, submission_id: str
    ) -> BordereauDetail | None:
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
        return BordereauDetail.model_validate(detail_payload)

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
            raise KeyError(f"no bordereau-reporting review item for submission '{submission_id}'")
        result = await self.review_queue.act(session, ctx, item.id, review_action)
        detail: dict[str, Any] = {"submission": submission_id, "action": action}
        await self.audit.record(session, ctx, AuditEntry(
            actor="human", who=ctx.user_id, what=f"{action} (role={ctx.role.value})",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail=detail))
        await session.commit()
        return {"id": result.id, "status": result.status.value}

    async def export_all_to_sheet(self, session: AsyncSession, ctx: Ctx) -> str:
        """Exports every bordereau currently in this tenant's list — regardless of
        review status — as one row each into the shared spreadsheet's "Bordereau
        Reporting" tab. Manual, button-triggered; never fails the caller."""
        sheet_id = await resolve_sheet_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        sheet_rows = [
            [r.id, r.carrierName, r.reportingPeriod, r.status] for r in rows
        ]
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_append_rows(
            connector, ctx, sheet_id, sheet_rows, tab=_SHEET_TAB, header=_SHEET_HEADER
        )

    async def export_all_to_drive(self, session: AsyncSession, ctx: Ctx) -> str:
        """Generates one PDF (one page per bordereau currently in this tenant's
        list, regardless of review status) and uploads it to the tenant's
        connected Drive. Manual, button-triggered."""
        folder_id = await resolve_drive_folder_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        pdf_rows = [
            [
                ("Bordereau ID", r.id), ("Carrier Name", r.carrierName),
                ("Reporting Period", r.reportingPeriod), ("Status", r.status),
            ]
            for r in rows
        ]
        pdf_bytes = render_bulk_summary_pdf("Bordereau Reporting", pdf_rows)
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        return await try_put_file(
            connector, ctx, folder_id, f"bordereau-reporting-{timestamp}.pdf",
            pdf_bytes, "application/pdf",
        )

    async def add_to_calendar(self, session: AsyncSession, ctx: Ctx, submission_id: str) -> str:
        """Creates (or updates) one all-day Google Calendar event for ONE bordereau
        — a per-item action, dated at that bordereau's own due date. Manual,
        button-triggered; never fails the caller: an unconnected Calendar
        integration is a normal, logged skip. The event's id is deterministic
        (derived from the bordereau id) so a repeat click updates the same event
        instead of duplicating it."""
        detail = await self.get_detail(session, ctx, submission_id)
        if detail is None:
            raise KeyError(f"no bordereau-reporting detail for submission '{submission_id}'")
        try:
            date.fromisoformat(detail.dueDate)
        except ValueError:
            return "skipped-no-due-date"
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_create_event(
            connector, ctx, f"bordereau-reporting-{submission_id}",
            summary=f"Bordereau due: {detail.carrierName} ({detail.reportingPeriod})",
            description=(
                f"Bordereau {submission_id} — {detail.carrierName}, reporting period "
                f"{detail.reportingPeriod}. Status: {detail.status}."
            ),
            start_date=detail.dueDate, end_date=detail.dueDate,
        )
