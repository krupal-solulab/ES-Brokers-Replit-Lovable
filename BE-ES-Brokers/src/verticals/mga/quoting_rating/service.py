"""Quoting & Rating Support pipeline — ingest(dataset fixture) → build a schedule
adjustment suggestion with grounding (QR-03/FR-4) → call the real RatingEngine directly
for the actual calculation (QR-01/02/03/04/06/07/08, never reimplemented) → itemized
worksheet → review → audit. No auto-finalization — the underwriter reviews the worksheet
and finalizes manually, same permanent boundary as every workflow in this project.
"""

from __future__ import annotations

import re
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
from core.extraction.service import coerce_number
from core.ingestion import (
    build_connector_service,
    resolve_drive_folder_id,
    resolve_sheet_id,
    try_append_rows,
    try_put_file,
)
from core.ingestion.pdf_export import render_bulk_summary_pdf
from core.models import Decision as DecisionRow
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.models import Submission
from core.review_queue import DefaultReviewQueueService
from verticals.mga.decision_core.rating import (
    RatingEngine,
    StateExposure,
    WorksheetInput,
    WorksheetResult,
)
from verticals.mga.models import MgaQuotingResult
from verticals.mga.quoting_rating.config import QuotingConfig
from verticals.mga.quoting_rating.fixtures import load_scenario
from verticals.mga.quoting_rating.normalize import normalize_class_code, normalize_states
from verticals.mga.quoting_rating.schema import (
    ActivityEntry,
    BenchmarkComparisonOut,
    StateCalculationOut,
    WorksheetDetail,
    WorksheetRow,
)

WORKFLOW = "quoting-rating"
_SHEET_TAB = "Quoting & Rating"
_SHEET_HEADER = ["ID", "Named Insured", "Class Code", "States", "Total Indicated Premium", "Status"]
TRIAGE_WORKFLOW = "submission-triage"

_ACTIONS = {
    "approve": ReviewAction.APPROVE,
    "send": ReviewAction.SEND,
    "escalate": ReviewAction.ESCALATE,
}


class QuotingService:
    def __init__(self) -> None:
        self.engine = RatingEngine()
        self.cfg = QuotingConfig()
        self.review_queue = DefaultReviewQueueService()
        self.audit = DefaultAuditService()

    async def process(
        self, session: AsyncSession, ctx: Ctx, scenario: str,
        request_override: dict[str, Any] | None = None,
    ) -> WorksheetDetail:
        request = request_override or load_scenario(scenario)
        if request is None:
            raise KeyError(f"no quoting fixture '{scenario}' for Workflow-05")

        sub = Submission(tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                         external_ref=scenario, subject=request.get("submission_id", scenario),
                         status="quoting")
        session.add(sub)
        await session.flush()

        worksheet_input = self._build_worksheet_input(request)
        return await self._persist(session, ctx, sub, scenario, request, worksheet_input)

    async def process_from_triage(
        self, session: AsyncSession, ctx: Ctx, submission_id: str,
        requested_adjustment_pct: float | None = None,
    ) -> WorksheetDetail:
        """QR's real trigger per the PRD: a submission reaches PROCEED in Submission
        Triage. Reads that submission's already-persisted Triage OutputPackage +
        Decision (no re-extraction, per FR-3/QR-02 Extraction Core reuse), normalizes
        the raw ``acord.class_code``/``acord.states_of_operation`` text into the bare
        code / USPS-abbreviation shape ``RatingConfig.filed_rate_plans`` is keyed on,
        and rates every named state independently (QR-06 — never blended).

        ``requested_adjustment_pct``, when given, is an underwriter-requested
        credit/debit that overrides the system-suggested one (``suggested_pct``, from
        already-extracted loss-trend data) — the engine's own QR-03 capping against
        each state's filed range still applies, so an out-of-range request comes back
        visibly capped, never silently clamped without saying so."""
        pkg = (await session.execute(
            select(OutputPackageRow).where(
                col(OutputPackageRow.tenant_id) == ctx.tenant_id,
                col(OutputPackageRow.submission_id) == submission_id,
                col(OutputPackageRow.workflow) == TRIAGE_WORKFLOW))
        ).scalars().first()
        if pkg is None or not pkg.payload:
            raise KeyError(f"no submission-triage output for submission '{submission_id}'")

        decision_row = (await session.execute(
            select(DecisionRow).where(
                col(DecisionRow.tenant_id) == ctx.tenant_id,
                col(DecisionRow.submission_id) == submission_id))
        ).scalars().first()
        if decision_row is None or decision_row.outcome != DecisionOutcome.PROCEED:
            raise ValueError(
                f"submission '{submission_id}' has not reached PROCEED in Submission "
                "Triage — Quoting & Rating only triggers off a clean triage decision")

        triage_detail = pkg.payload["detail"]
        by_name = {f["key"]: f["value"] for f in triage_detail.get("fields", [])}
        triage_row = pkg.payload.get("row", {})

        def field(*suffixes: str) -> str | None:
            """A plain-text submission email rarely says the word "ACORD" or "financial
            statement" — which DocumentKind wins the keyword classification (acord vs.
            financials) is an accident of phrasing, not something this workflow should
            depend on. Check every DocumentKind prefix Triage might have used for each
            of these labels rather than assuming one specific kind classified them."""
            for kind in ("acord", "financials", "other"):
                for suffix in suffixes:
                    value = by_name.get(f"{kind}.{suffix}")
                    if value:
                        return str(value)
            return None

        request = {
            "submission_id": submission_id,
            "named_insured": triage_row.get("insured", ""),
            "class_code": normalize_class_code(field("class_code") or ""),
            "extracted_factors": {
                "loss_history_trend": str(by_name.get("loss_run.loss_frequency_trend") or ""),
            },
        }
        states_raw = field("states_of_operation") or ""
        state_codes = normalize_states(states_raw)
        revenue = coerce_number(field("stated_annual_revenue", "total_revenue"))
        prior_premium = coerce_number(field("prior_premium", "prior_annual_premium"))

        if not state_codes:
            raise ValueError(
                f"submission '{submission_id}' names no recognized US state "
                f"('{states_raw}') — cannot resolve a filed rate plan")

        suggested_pct, grounding = self._suggest_adjustment(request)
        # A multi-state submission's revenue is its TOTAL exposure across every state —
        # splitting it evenly per state is the only allocation Triage's extraction
        # actually supports (it has no per-state revenue breakdown); QR-06 still rates
        # each state independently against its own filed plan once allocated.
        per_state_exposure = (revenue or 0.0) / len(state_codes)
        states = [StateExposure(state=code, exposure_amount=per_state_exposure) for code in state_codes]
        worksheet_input = WorksheetInput(
            class_code=request["class_code"], states=states,
            requested_adjustment_pct=requested_adjustment_pct,
            suggested_adjustment_pct=suggested_pct, adjustment_grounding=grounding,
            prior_expiring_premium=prior_premium)

        sub = Submission(tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                         external_ref=submission_id, subject=request["named_insured"] or submission_id,
                         status="quoting")
        session.add(sub)
        await session.flush()
        return await self._persist(session, ctx, sub, submission_id, request, worksheet_input)

    async def _persist(
        self, session: AsyncSession, ctx: Ctx, sub: Submission, ref: str,
        request: dict[str, Any], worksheet_input: WorksheetInput,
    ) -> WorksheetDetail:
        result = self.engine.calculate_worksheet(worksheet_input)
        detail = self._build_detail(sub.id, ref, request, result)

        session.add(MgaQuotingResult(
            tenant_id=ctx.tenant_id, submission_id=sub.id, class_code=request.get("class_code", ""),
            status=result.status, total_indicated_premium=result.total_indicated_premium,
            benchmark_flagged=result.benchmark_flagged_for_review,
            any_adjustment_capped=any(s.adjustment_capped for s in result.state_calculations),
            any_minimum_applied=any(s.minimum_premium_applied for s in result.state_calculations)))

        out_dto = OutputPackageDTO(
            submission_id=sub.id,
            decision=DecisionDTO(
                outcome=(DecisionOutcome.PROCEED if result.status == "READY_FOR_REVIEW"
                        else DecisionOutcome.REQUEST_INFO),
                score=None, rationale=self._rationale(result)),
            draft=Draft(text=self._rationale(result), citations=[]),
            flags=[result.status], missing_info=[],
            payload={"detail": detail.model_dump(by_alias=True)})
        await self.review_queue.enqueue(session, ctx, out_dto, WORKFLOW)

        await self.audit.record(session, ctx, AuditEntry(
            actor="ai", who="system", what=f"Rating worksheet calculated: {result.status}",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"scenario": ref, "status": result.status}))
        await session.commit()
        return detail

    def _build_worksheet_input(self, request: dict[str, Any]) -> WorksheetInput:
        class_code = str(request.get("class_code", ""))
        prior_premium = request.get("prior_expiring_premium")

        multi_state = request.get("multi_state_exposure")
        if multi_state:
            states = [
                StateExposure(
                    state=s["state"], exposure_amount=s["allocated_revenue"],
                    rate_plan_version=s.get("rate_plan_version"),
                    filed_status="currently filed and approved",
                    base_rate_per_1000_exposure=s.get("base_rate_per_1000_revenue"))
                for s in multi_state
            ]
            return WorksheetInput(class_code=class_code, states=states,
                                  prior_expiring_premium=prior_premium)

        # stale rate-plan lookup result (scenario_06 shape) — an explicit per-state
        # override that carries its own (superseded) version/status/rate.
        lookup = request.get("rate_plan_lookup_result")
        exposure = request.get("exposure_basis", {})
        state = str(request.get("state", ""))
        if lookup is not None:
            states = [StateExposure(
                state=state, exposure_amount=exposure.get("amount", 0.0),
                rate_plan_version=lookup.get("version_found"),
                filed_status=lookup.get("filed_status", ""),
                base_rate_per_1000_exposure=lookup.get("base_rate_per_1000_revenue_old_version"))]
            return WorksheetInput(class_code=class_code, states=states,
                                  prior_expiring_premium=prior_premium)

        # single-state, resolve against the config table (no explicit rate_plan in the
        # request beyond what's already filed — matches scenario_01/02/03/04's shape).
        suggested_pct, grounding = self._suggest_adjustment(request)
        requested_pct = self._requested_adjustment(request)
        states = [StateExposure(state=state, exposure_amount=exposure.get("amount", 0.0))]
        return WorksheetInput(
            class_code=class_code, states=states, requested_adjustment_pct=requested_pct,
            suggested_adjustment_pct=suggested_pct, adjustment_grounding=grounding,
            prior_expiring_premium=prior_premium)

    def _suggest_adjustment(self, request: dict[str, Any]) -> tuple[float | None, str | None]:
        """QR-03/FR-4: suggest a specific adjustment only when a grounded basis exists in
        already-extracted data — never suggest one without a stated reason."""
        factors = request.get("extracted_factors", {})
        trend = str(factors.get("loss_history_trend", "")).lower()
        if any(k in trend for k in self.cfg.improving_trend_keywords):
            basis = [factors.get("loss_history_trend", "")]
            pct = self.cfg.improving_credit_pct
            if factors.get("safety_program_documented"):
                basis.append("documented safety program")
                pct += self.cfg.safety_program_extra_credit_pct
            return pct, " + ".join(str(b) for b in basis)
        if any(k in trend for k in self.cfg.worsening_trend_keywords):
            return self.cfg.worsening_debit_pct, str(factors.get("loss_history_trend", ""))
        return None, None

    @staticmethod
    def _requested_adjustment(request: dict[str, Any]) -> float | None:
        """An underwriter's explicit requested adjustment, per the dataset's
        ``underwriter_note`` free-text field (scenario_03's shape)."""
        note = str(request.get("extracted_factors", {}).get("underwriter_note", ""))
        m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", note)
        return float(m.group(1)) if m else None

    @staticmethod
    def _rationale(result: WorksheetResult) -> str:
        if result.status == "BLOCKED_STALE_RATE_PLAN":
            reasons = [s.blocked_reason for s in result.state_calculations if s.blocked_reason]
            return "; ".join(reasons) or "Blocked — stale rate plan."
        parts = []
        for s in result.state_calculations:
            if s.adjustment_capped:
                parts.append(
                    f"{s.state}: requested {s.requested_adjustment_pct:+.0f}% exceeds the "
                    f"filed range — capped at {s.applied_adjustment_pct:+.0f}%.")
            if s.minimum_premium_applied:
                parts.append(f"{s.state}: minimum premium floor applied.")
        if result.benchmark_flagged_for_review:
            parts.append(
                "Indicated premium differs materially from the benchmark — flagged for review.")
        return " ".join(parts) or (
            "Straightforward, transparent worksheet — no adjustments or flags.")

    def _build_detail(
        self, sub_id: str, scenario: str, request: dict[str, Any], result: WorksheetResult,
    ) -> WorksheetDetail:
        now = datetime.now(UTC).isoformat()
        return WorksheetDetail(
            worksheetId=f"QR-{sub_id[-6:]}",
            submissionId=str(request.get("submission_id", sub_id)),
            namedInsured=str(request.get("named_insured", "")),
            classCode=str(request.get("class_code", "")),
            stateCalculations=[
                StateCalculationOut(
                    state=s.state, ratePlanVersionUsed=s.rate_plan_version,
                    ratePlanCurrencyCheck=s.rate_plan_currency_check,
                    allocatedExposure=s.allocated_exposure, basePremium=s.base_premium,
                    suggestedAdjustmentPct=s.suggested_adjustment_pct,
                    adjustmentGrounding=s.adjustment_grounding,
                    requestedAdjustmentPct=s.requested_adjustment_pct,
                    appliedAdjustmentPct=s.applied_adjustment_pct,
                    adjustmentCapped=s.adjustment_capped,
                    premiumAfterAdjustment=s.premium_after_adjustment,
                    minimumPremiumApplied=s.minimum_premium_applied,
                    finalStatePremium=s.final_state_premium, blockedReason=s.blocked_reason)
                for s in result.state_calculations
            ],
            totalIndicatedPremium=result.total_indicated_premium,
            benchmarkComparison=BenchmarkComparisonOut(
                priorPremium=result.benchmark_prior_premium,
                pctVariance=result.benchmark_pct_variance,
                flaggedForReview=result.benchmark_flagged_for_review),
            status=result.status,
            activity=[ActivityEntry(at=now, who="system (AI)",
                                    what=f"Worksheet calculated -> {result.status}", ctx=scenario)],
        )

    # ── list / detail / act ──
    async def list_rows(self, session: AsyncSession, ctx: Ctx) -> list[WorksheetRow]:
        stmt = (select(ReviewItemRow, OutputPackageRow)
                .join(OutputPackageRow,
                      col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
                .where(col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                       col(ReviewItemRow.workflow) == WORKFLOW))
        rows: list[WorksheetRow] = []
        for item, pkg in (await session.execute(stmt)).all():
            payload = pkg.payload or {}
            if "detail" not in payload:
                continue
            d = WorksheetDetail.model_validate(payload["detail"])
            total = (f"${d.totalIndicatedPremium:,.0f}"
                    if d.totalIndicatedPremium is not None else "—")
            review_status = item.status.value if hasattr(item.status, "value") else str(item.status)
            rows.append(WorksheetRow(
                id=pkg.submission_id, namedInsured=d.namedInsured, classCode=d.classCode,
                states=", ".join(s.state for s in d.stateCalculations),
                totalIndicatedPremium=total, status=d.status, reviewStatus=review_status))
        return rows

    async def get_detail(
        self, session: AsyncSession, ctx: Ctx, submission_id: str
    ) -> WorksheetDetail | None:
        row = (await session.execute(
            select(ReviewItemRow, OutputPackageRow)
            .join(OutputPackageRow,
                  col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
            .where(col(OutputPackageRow.tenant_id) == ctx.tenant_id,
                   col(OutputPackageRow.submission_id) == submission_id,
                   col(OutputPackageRow.workflow) == WORKFLOW))
        ).first()
        if row is None or not row[1].payload:
            return None
        item, pkg = row
        detail = WorksheetDetail.model_validate(pkg.payload["detail"])
        detail.reviewStatus = item.status.value if hasattr(item.status, "value") else str(item.status)
        return detail

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
            raise KeyError(f"no quoting-rating review item for submission '{submission_id}'")
        result = await self.review_queue.act(session, ctx, item.id, review_action)
        await self.audit.record(session, ctx, AuditEntry(
            actor="human", who=ctx.user_id, what=f"{action} (role={ctx.role.value})",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"submission": submission_id, "action": action}))
        await session.commit()
        return {"id": result.id, "status": result.status.value}

    async def export_all_to_sheet(self, session: AsyncSession, ctx: Ctx) -> str:
        """Exports every worksheet currently in this tenant's list — regardless of
        review status — as one row each into the shared spreadsheet's "Quoting &
        Rating" tab. Manual, button-triggered; never fails the caller."""
        sheet_id = await resolve_sheet_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        sheet_rows = [
            [r.id, r.namedInsured, r.classCode, r.states, r.totalIndicatedPremium, r.status]
            for r in rows
        ]
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_append_rows(
            connector, ctx, sheet_id, sheet_rows, tab=_SHEET_TAB, header=_SHEET_HEADER
        )

    async def export_all_to_drive(self, session: AsyncSession, ctx: Ctx) -> str:
        """Generates one PDF (one page per worksheet currently in this tenant's
        list, regardless of review status) and uploads it to the tenant's
        connected Drive. Manual, button-triggered."""
        folder_id = await resolve_drive_folder_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        pdf_rows = [
            [
                ("ID", r.id), ("Named Insured", r.namedInsured),
                ("Class Code", r.classCode), ("States", r.states),
                ("Total Indicated Premium", r.totalIndicatedPremium), ("Status", r.status),
            ]
            for r in rows
        ]
        pdf_bytes = render_bulk_summary_pdf("Quoting & Rating", pdf_rows)
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        return await try_put_file(
            connector, ctx, folder_id, f"quoting-rating-{timestamp}.pdf",
            pdf_bytes, "application/pdf",
        )
