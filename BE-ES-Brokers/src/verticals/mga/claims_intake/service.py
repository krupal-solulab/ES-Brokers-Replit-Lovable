"""Claims Intake Coordination pipeline — ingest(dataset fixture) -> triage
(CLI-01/02/04/07/08) -> review -> audit. FNOL intake is triaged and routed only — no
claim is ever auto-settled, auto-closed, or auto-sent here; every routing decision is
human-reviewed before it goes out, same permanent human-approval boundary as every
other MGA workflow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
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
from verticals.mga.claims_intake.engine import (
    EXCEEDS_AUTHORITY,
    NO_AUTHORITY_DELEGATED,
    BLOCKED,
    ClaimsIntakeDecision,
    ClaimsIntakeEngine,
)
from verticals.mga.claims_intake.fixtures import load_scenario
from verticals.mga.claims_intake.schema import (
    ActivityEntry,
    ClaimsIntakeDetail,
    ClaimsIntakeRow,
    PhiGateOut,
    ProceduralSignalOut,
    SettlementAuthorityCheckOut,
    WriteBackRecordOut,
)
from verticals.mga.models import MgaClaimsIntakeResult

WORKFLOW = "claims-intake"
_SHEET_TAB = "Claims Intake"
_SHEET_HEADER = ["ID", "Policy", "Insured", "Carrier", "Authority Classification", "Routing Outcome", "Status"]

_ACTIONS = {
    "approve": ReviewAction.APPROVE,
    "send": ReviewAction.SEND,       # human-triggered dispatch to carrier/TPA
    "escalate": ReviewAction.ESCALATE,
}

_STATUS_BY_OUTCOME = {
    NO_AUTHORITY_DELEGATED: "FORWARD_ONLY",
    EXCEEDS_AUTHORITY: "MUST_REFER",
}


class ClaimsIntakeService:
    def __init__(self) -> None:
        self.engine = ClaimsIntakeEngine()
        self.review_queue = DefaultReviewQueueService()
        self.audit = DefaultAuditService()

    async def process(
        self, session: AsyncSession, ctx: Ctx, scenario: str,
        request_override: dict[str, Any] | None = None,
    ) -> ClaimsIntakeDetail:
        request = request_override or load_scenario(scenario)
        if request is None:
            raise KeyError(f"no claims-intake fixture '{scenario}' for Workflow-10")

        sub = Submission(
            tenant_id=ctx.tenant_id, vertical=ctx.vertical, external_ref=scenario,
            subject=str(request.get("named_insured", scenario)), status="claims-intake")
        session.add(sub)
        await session.flush()

        decision = self.engine.decide(request)
        detail = self._build_detail(sub.id, scenario, request, decision)
        row = self._build_row(sub.id, request, detail)

        session.add(MgaClaimsIntakeResult(
            tenant_id=ctx.tenant_id, submission_id=sub.id,
            authority_classification=decision.authority_classification,
            routing_outcome=decision.routing_outcome, carrier=decision.carrier,
            claim_number=decision.write_back_record.claim_number,
            coverage_matched=(decision.authority_classification != NO_AUTHORITY_DELEGATED),
            exceeds_settlement_ceiling=(
                decision.settlement_authority_check.within_ceiling is False),
            phi_blocked=(decision.phi_gate.medical_content_processing_status == BLOCKED),
            incurred_estimate=decision.settlement_authority_check.estimated_reserve))

        out_dto = OutputPackageDTO(
            submission_id=sub.id,
            decision=DecisionDTO(
                outcome=(DecisionOutcome.DECLINE
                        if decision.authority_classification in (NO_AUTHORITY_DELEGATED, EXCEEDS_AUTHORITY)
                        else DecisionOutcome.PROCEED),
                score=None, rationale=decision.rationale),
            draft=Draft(text=decision.rationale, citations=[]),
            flags=[decision.routing_outcome, decision.authority_classification], missing_info=[],
            payload={"detail": detail.model_dump(by_alias=True), "row": row.model_dump()})
        await self.review_queue.enqueue(session, ctx, out_dto, WORKFLOW)

        await self.audit.record(session, ctx, AuditEntry(
            actor="ai", who="system", what=f"FNOL triaged: {decision.routing_outcome}",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"scenario": scenario, "routing": decision.routing_outcome,
                    "authority": decision.authority_classification}))
        await session.commit()
        return detail

    def _build_detail(
        self, sub_id: str, scenario: str, request: dict[str, Any],
        decision: ClaimsIntakeDecision,
    ) -> ClaimsIntakeDetail:
        now = datetime.now(UTC).isoformat()
        status = _STATUS_BY_OUTCOME.get(decision.authority_classification, "READY_FOR_INTERNAL_HANDLING")
        if decision.phi_gate.medical_content_processing_status == BLOCKED:
            status = "PHI_BLOCKED"

        return ClaimsIntakeDetail(
            claimId=f"MCI-{sub_id[-6:]}",
            policyNumber=request.get("policy_number"),
            namedInsured=str(request.get("named_insured", "")),
            carrier=decision.carrier,
            lossDescription=str(request.get("loss_description", "")),
            authorityClassification=decision.authority_classification,
            bodilyInjuryInvolved=decision.bodily_injury_involved,
            phiGate=PhiGateOut(
                triggered=decision.phi_gate.triggered,
                baaConfirmed=decision.phi_gate.baa_confirmed,
                medicalContentProcessingStatus=decision.phi_gate.medical_content_processing_status),
            settlementAuthorityCheck=SettlementAuthorityCheckOut(
                estimatedReserve=decision.settlement_authority_check.estimated_reserve,
                ceiling=decision.settlement_authority_check.ceiling,
                withinCeiling=decision.settlement_authority_check.within_ceiling),
            proceduralSignals=[
                ProceduralSignalOut(description=s.description, loggedOnly=s.logged_only)
                for s in decision.procedural_signals
            ],
            writeBackRecord=WriteBackRecordOut(
                logged=decision.write_back_record.logged,
                bordereauSchemaValidated=decision.write_back_record.bordereau_schema_validated,
                claimNumber=decision.write_back_record.claim_number),
            routingOutcome=decision.routing_outcome,
            rationale=decision.rationale,
            status=status,
            activity=[ActivityEntry(at=now, who="system (AI)",
                                    what=f"FNOL triaged -> {decision.routing_outcome}",
                                    ctx=scenario)],
        )

    @staticmethod
    def _build_row(
        sub_id: str, request: dict[str, Any], detail: ClaimsIntakeDetail,
    ) -> ClaimsIntakeRow:
        return ClaimsIntakeRow(
            id=sub_id, policy=detail.policyNumber,
            insured=str(request.get("named_insured", "")), carrier=detail.carrier,
            authorityClassification=detail.authorityClassification,
            routingOutcome=detail.routingOutcome, status="pending")

    # ── list / detail / act ──
    async def list_rows(self, session: AsyncSession, ctx: Ctx) -> list[ClaimsIntakeRow]:
        stmt = (select(ReviewItemRow, OutputPackageRow)
                .join(OutputPackageRow,
                      col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
                .where(col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                       col(ReviewItemRow.workflow) == WORKFLOW))
        rows: list[ClaimsIntakeRow] = []
        for item, pkg in (await session.execute(stmt)).all():
            payload = pkg.payload or {}
            if "row" not in payload:
                continue
            try:
                row = ClaimsIntakeRow(**payload["row"])
            except ValidationError:
                # A row persisted by an older schema version (missing a field this
                # version requires) shouldn't take down the whole list — skip it,
                # same as the "row" key missing entirely, above.
                continue
            row.status = item.status.value if hasattr(item.status, "value") else str(item.status)
            rows.append(row)
        return rows

    async def get_detail(
        self, session: AsyncSession, ctx: Ctx, submission_id: str
    ) -> ClaimsIntakeDetail | None:
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
        return ClaimsIntakeDetail.model_validate(detail_payload)

    async def act(
        self, session: AsyncSession, ctx: Ctx, submission_id: str, action: str,
        note: str | None = None,
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
            raise KeyError(f"no claims-intake review item for submission '{submission_id}'")
        result = await self.review_queue.act(session, ctx, item.id, review_action)
        detail: dict[str, Any] = {"submission": submission_id, "action": action}
        if note:
            detail["note"] = note
        await self.audit.record(session, ctx, AuditEntry(
            actor="human", who=ctx.user_id, what=f"{action} (role={ctx.role.value})",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail=detail))
        await session.commit()
        return {"id": result.id, "status": result.status.value}

    async def export_all_to_sheet(self, session: AsyncSession, ctx: Ctx) -> str:
        """Exports every claim currently in this tenant's list — regardless of
        review status — as one row each into the shared spreadsheet's "Claims
        Intake" tab. Manual, button-triggered; never fails the caller."""
        sheet_id = await resolve_sheet_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        sheet_rows = [
            [
                r.id, r.policy, r.insured, r.carrier, r.authorityClassification,
                r.routingOutcome, r.status,
            ]
            for r in rows
        ]
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_append_rows(
            connector, ctx, sheet_id, sheet_rows, tab=_SHEET_TAB, header=_SHEET_HEADER
        )

    async def export_all_to_drive(self, session: AsyncSession, ctx: Ctx) -> str:
        """Generates one PDF (one page per claim currently in this tenant's list,
        regardless of review status) and uploads it to the tenant's connected
        Drive. Manual, button-triggered."""
        folder_id = await resolve_drive_folder_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        pdf_rows = [
            [
                ("ID", r.id), ("Policy", r.policy or "—"), ("Insured", r.insured),
                ("Carrier", r.carrier or "—"), ("Authority Classification", r.authorityClassification),
                ("Routing Outcome", r.routingOutcome), ("Status", r.status),
            ]
            for r in rows
        ]
        pdf_bytes = render_bulk_summary_pdf("Claims Intake", pdf_rows)
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        return await try_put_file(
            connector, ctx, folder_id, f"claims-intake-{timestamp}.pdf",
            pdf_bytes, "application/pdf",
        )
