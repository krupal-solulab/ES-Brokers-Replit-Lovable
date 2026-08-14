"""Bind Order & Issuance pipeline — ingest(dataset fixture) → worksheet fidelity gate
(MBI-01) → pre-bind subjectivity gate (MBI-02) → final authority reconfirmation against
current information (MBI-03) → PAS write-back (MBI-04) → issuance reconciliation
(MBI-05) → downstream trigger gating (MBI-06) → post-bind obligation tracking (MBI-07)
→ review → audit. Orchestration layer over Quoting & Rating Support (the worksheet this
workflow binds against — no independent premium entry) and Endorsement Processing's
write-back/referral patterns, per the PRD. No auto-binding, no auto-resolved discrepancy
— human approves every bind order and resolves every flagged discrepancy.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.audit import DefaultAuditService
from core.common.dtos import AuditEntry, Ctx, Draft
from core.common.dtos import Decision as DecisionDTO
from core.common.dtos import OutputPackage as OutputPackageDTO
from core.common.enums import DecisionOutcome, ReviewAction, ReviewStatus
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
from verticals.mga.bind_issuance.authority_lookup import lookup_authority
from verticals.mga.bind_issuance.engine import READY, BindDecision, BindIssuanceEngine
from verticals.mga.bind_issuance.fixtures import load_scenario
from verticals.mga.bind_issuance.schema import (
    ActivityEntry,
    AuthorityReconfirmationOut,
    BindDetail,
    BindRow,
    DiscrepancyOut,
    DownstreamTriggersOut,
    IssuanceReconciliationOut,
    PostBindObligationOut,
    StalenessCheckOut,
    SubjectivityOut,
    WorksheetReferenceOut,
    WriteBackOut,
)
from verticals.mga.models import MgaBindResult, MgaPremiumLedger

WORKFLOW = "bind-issuance"
QUOTING_WORKFLOW = "quoting-rating"
_SHEET_TAB = "Bind Issuance"
_SHEET_HEADER = ["Bind ID", "Named Insured", "Premium", "Status", "Review Status"]

_ACTIONS = {
    "approve": ReviewAction.APPROVE,
    "send": ReviewAction.SEND,       # human-triggered carrier referral send
    "escalate": ReviewAction.ESCALATE,
}


class BindIssuanceService:
    def __init__(self) -> None:
        self.engine = BindIssuanceEngine()
        self.review_queue = DefaultReviewQueueService()
        self.audit = DefaultAuditService()

    async def process(
        self, session: AsyncSession, ctx: Ctx, scenario: str,
        request_override: dict[str, Any] | None = None,
    ) -> BindDetail:
        request = request_override or load_scenario(scenario)
        if request is None:
            raise KeyError(f"no bind/issuance fixture '{scenario}' for Workflow-06")

        sub = Submission(tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                         external_ref=scenario, subject=request.get("submission_id", scenario),
                         status="binding")
        session.add(sub)
        await session.flush()

        decision = self.engine.decide(request)
        detail = self._build_detail(sub.id, scenario, request, decision)

        bind_result = MgaBindResult(
            tenant_id=ctx.tenant_id, submission_id=sub.id, status=decision.status,
            authority_outcome=decision.authority_outcome,
            write_back_logged=decision.write_back_logged,
            issuance_status=decision.issuance_status,
            # class_code isn't in scope here (only process_from_quoting resolves it via
            # a real worksheet) — the fixture's own request dict carries it directly.
            class_code=request.get("finalized_worksheet", {}).get("class_code"),
            carrier=request.get("delegated_authority", {}).get("carrier") or None,
            issuance_discrepancy_count=len(decision.issuance_discrepancies),
            post_bind_obligation_count=len(decision.post_bind_obligations))
        session.add(bind_result)
        await session.flush()
        self._write_premium_ledger(session, ctx, sub.id, bind_result, decision, request)

        out_dto = OutputPackageDTO(
            submission_id=sub.id,
            decision=DecisionDTO(
                outcome=(DecisionOutcome.PROCEED if decision.status == READY
                        else DecisionOutcome.DECLINE),
                score=None, rationale=decision.rationale),
            draft=Draft(text=decision.rationale, citations=[]),
            flags=[decision.status], missing_info=[],
            payload={"detail": detail.model_dump(by_alias=True)})
        await self.review_queue.enqueue(session, ctx, out_dto, WORKFLOW)

        await self.audit.record(session, ctx, AuditEntry(
            actor="ai", who="system", what=f"Bind order evaluated: {decision.status}",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"scenario": scenario, "status": decision.status}))
        await session.commit()
        return detail

    @staticmethod
    def _write_premium_ledger(
        session: AsyncSession, ctx: Ctx, submission_id: str, bind_result: MgaBindResult,
        decision: BindDecision, request: dict[str, Any],
    ) -> None:
        """A ledger row represents a real bound premium — only write one when the bind
        actually went through (READY), never for a BLOCKED order whose premium was
        never actually put on risk."""
        if decision.status != READY or decision.worksheet_premium is None:
            return
        session.add(MgaPremiumLedger(
            tenant_id=ctx.tenant_id, submission_id=submission_id, bind_result_id=bind_result.id,
            class_code=bind_result.class_code, carrier=bind_result.carrier,
            premium=decision.worksheet_premium,
            effective_date=request.get("finalized_worksheet", {}).get("effective_date")))

    async def process_from_quoting(
        self, session: AsyncSession, ctx: Ctx, submission_id: str,
    ) -> BindDetail:
        """Bind & Issuance's real trigger per the PRD: "a finalized Quoting & Rating
        Support worksheet is accepted...and a bind request is initiated" — not merely a
        worksheet that calculated cleanly, but one the underwriter has actually approved
        (its ReviewItem status), since MBI-01 never allows binding on an unfinalized
        figure. Reads that worksheet back verbatim (no premium recomputation here — any
        change must go back through Quoting & Rating's own engine, per MBI-01)."""
        row = (await session.execute(
            select(ReviewItemRow, OutputPackageRow)
            .join(OutputPackageRow,
                  col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
            .where(col(OutputPackageRow.tenant_id) == ctx.tenant_id,
                   col(OutputPackageRow.submission_id) == submission_id,
                   col(OutputPackageRow.workflow) == QUOTING_WORKFLOW))
        ).first()
        if row is None or not row[1].payload:
            raise KeyError(f"no quoting-rating output for submission '{submission_id}'")
        item, pkg = row
        if item.status != ReviewStatus.APPROVED:
            raise ValueError(
                f"worksheet for submission '{submission_id}' has not been finalized "
                "(approved) in Quoting & Rating — Bind & Issuance only binds against an "
                "underwriter-accepted worksheet, never a worksheet still under review")

        worksheet = pkg.payload["detail"]
        if worksheet.get("status") != "READY_FOR_REVIEW":
            raise ValueError(
                f"worksheet for submission '{submission_id}' is not READY_FOR_REVIEW "
                f"(status={worksheet.get('status')}) — cannot bind against a blocked worksheet")

        class_code = str(worksheet.get("classCode", ""))
        authority = lookup_authority(class_code)
        premium = worksheet.get("totalIndicatedPremium")

        request: dict[str, Any] = {
            "submission_id": submission_id,
            "named_insured": worksheet.get("namedInsured", ""),
            "finalized_worksheet": {
                "worksheet_id": worksheet.get("worksheetId"),
                "worksheet_date": datetime.now(UTC).date().isoformat(),
                "total_indicated_premium": premium,
                "class_code": class_code,
            },
            # No delegated-authority table exists for classes outside the seeded
            # dataset yet — an honest empty ceiling (not a fabricated one) routes to
            # BLOCKED via MBI-03 rather than silently approving against a made-up cap.
            "delegated_authority": authority or {"carrier": "", "premium_ceiling": 0},
            # No pre-bind-subjectivity tracking exists upstream yet (Quoting & Rating
            # carries none) — an empty list is the honest state, not a fabricated clear.
            "pre_bind_subjectivities": [],
        }

        sub = Submission(tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                         external_ref=submission_id, subject=request["named_insured"] or submission_id,
                         status="binding")
        session.add(sub)
        await session.flush()

        decision = self.engine.decide(request)
        detail = self._build_detail(sub.id, submission_id, request, decision)
        # _build_detail's submissionId falls back to request["submission_id"], which is
        # the upstream Quoting & Rating submission id, not this new Bind row's own id —
        # override so the FE's row lookup (keyed by the real bind-issuance submission_id
        # via list_rows/get_detail) matches what's returned here.
        detail.submissionId = sub.id

        bind_result = MgaBindResult(
            tenant_id=ctx.tenant_id, submission_id=sub.id, status=decision.status,
            authority_outcome=decision.authority_outcome,
            write_back_logged=decision.write_back_logged,
            issuance_status=decision.issuance_status,
            class_code=class_code or None, carrier=(authority or {}).get("carrier") or None,
            issuance_discrepancy_count=len(decision.issuance_discrepancies),
            post_bind_obligation_count=len(decision.post_bind_obligations))
        session.add(bind_result)
        await session.flush()
        # No effective_date source exists on this live path yet — Quoting & Rating's
        # WorksheetDetail carries no such field (see MgaPremiumLedger's own docstring).
        self._write_premium_ledger(session, ctx, sub.id, bind_result, decision, request)

        out_dto = OutputPackageDTO(
            submission_id=sub.id,
            decision=DecisionDTO(
                outcome=(DecisionOutcome.PROCEED if decision.status == READY
                        else DecisionOutcome.DECLINE),
                score=None, rationale=decision.rationale),
            draft=Draft(text=decision.rationale, citations=[]),
            flags=[decision.status], missing_info=[],
            payload={"detail": detail.model_dump(by_alias=True)})
        await self.review_queue.enqueue(session, ctx, out_dto, WORKFLOW)

        await self.audit.record(session, ctx, AuditEntry(
            actor="ai", who="system", what=f"Bind order evaluated: {decision.status}",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"submission_id": submission_id, "status": decision.status}))
        await session.commit()
        return detail

    def _build_detail(
        self, sub_id: str, scenario: str, request: dict[str, Any], decision: BindDecision,
    ) -> BindDetail:
        now = datetime.now(UTC).isoformat()

        worksheet_ref = (
            WorksheetReferenceOut(worksheetId=decision.worksheet_id,
                                  worksheetDate=decision.worksheet_date,
                                  premium=decision.worksheet_premium)
            if decision.worksheet_id is not None else None)
        staleness = (
            StalenessCheckOut(daysSinceWorksheet=decision.days_since_worksheet,
                              exceedsThreshold=decision.exceeds_staleness_threshold,
                              materialUpdateLoggedSince=decision.material_update_logged_since)
            if decision.worksheet_id is not None else None)
        authority = (
            AuthorityReconfirmationOut(
                outcome=decision.authority_outcome, checkedPremium=decision.checked_premium,
                delegatedCeiling=decision.delegated_ceiling,
                referralDraftText=decision.referral_draft_text)
            if decision.authority_outcome is not None else None)

        return BindDetail(
            bindId=f"BND-{sub_id[-6:]}",
            submissionId=str(request.get("submission_id", sub_id)),
            namedInsured=str(request.get("named_insured", "")),
            worksheetReference=worksheet_ref,
            stalenessCheck=staleness,
            preBindSubjectivities=[
                SubjectivityOut(description=s.description, materiality=s.materiality,
                               status=s.status, lifecycleStage=s.lifecycle_stage)
                for s in decision.pre_bind_subjectivities
            ],
            authorityReconfirmation=authority,
            bindOrderStatus=decision.status,
            pasWriteBack=WriteBackOut(logged=decision.write_back_logged,
                                      bordereauSchemaValidated=decision.write_back_logged),
            issuanceReconciliation=IssuanceReconciliationOut(
                status=decision.issuance_status,
                discrepancyDetail=[
                    DiscrepancyOut(field=d.field, bound=d.bound, issued=d.issued)
                    for d in decision.issuance_discrepancies
                ]),
            postBindObligations=[
                PostBindObligationOut(
                    description=o.description, dueDate=o.due_date, status="open",
                    reminderDaysBefore=list(o.reminder_days_before))
                for o in decision.post_bind_obligations
            ],
            downstreamTriggersFired=DownstreamTriggersOut(
                bindConfirmation=decision.bind_confirmation_fired,
                policyDelivered=decision.policy_delivered_fired),
            rationale=decision.rationale,
            activity=[ActivityEntry(at=now, who="system (AI)",
                                    what=f"Bind order evaluated -> {decision.status}",
                                    ctx=scenario)],
        )

    # ── list / detail / act ──
    async def list_rows(self, session: AsyncSession, ctx: Ctx) -> list[BindRow]:
        stmt = (select(ReviewItemRow, OutputPackageRow)
                .join(OutputPackageRow,
                      col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
                .where(col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                       col(ReviewItemRow.workflow) == WORKFLOW))
        rows: list[BindRow] = []
        for item, pkg in (await session.execute(stmt)).all():
            payload = pkg.payload or {}
            if "detail" not in payload:
                continue
            d = BindDetail.model_validate(payload["detail"])
            premium = (f"${d.worksheetReference.premium:,.0f}"
                      if d.worksheetReference is not None else "—")
            review_status = item.status.value if hasattr(item.status, "value") else str(item.status)
            rows.append(BindRow(id=pkg.submission_id, namedInsured=d.namedInsured,
                                premium=premium, status=d.bindOrderStatus,
                                reviewStatus=review_status))
        return rows

    async def get_detail(
        self, session: AsyncSession, ctx: Ctx, submission_id: str
    ) -> BindDetail | None:
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
        return BindDetail.model_validate(detail_payload)

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
            raise KeyError(f"no bind-issuance review item for submission '{submission_id}'")
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
        """Exports every bind order currently in this tenant's list — regardless of
        review status — as one row each into the shared spreadsheet's "Bind
        Issuance" tab. Manual, button-triggered; never fails the caller: an unset
        sheet id or unconnected Sheets integration is a normal, logged skip."""
        sheet_id = await resolve_sheet_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        sheet_rows = [
            [r.id, r.namedInsured, r.premium, r.status, r.reviewStatus] for r in rows
        ]
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_append_rows(
            connector, ctx, sheet_id, sheet_rows, tab=_SHEET_TAB, header=_SHEET_HEADER
        )

    async def export_all_to_drive(self, session: AsyncSession, ctx: Ctx) -> str:
        """Generates one PDF (one page per bind order currently in this tenant's
        list, regardless of review status) and uploads it to the tenant's
        connected Drive. Manual, button-triggered. Never fails the caller: an
        unconnected Drive integration is a normal, logged skip; a missing folder
        id just uploads to Drive root."""
        folder_id = await resolve_drive_folder_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        pdf_rows = [
            [
                ("Bind ID", r.id), ("Named Insured", r.namedInsured),
                ("Premium", r.premium), ("Status", r.status),
                ("Review Status", r.reviewStatus),
            ]
            for r in rows
        ]
        pdf_bytes = render_bulk_summary_pdf("Bind Issuance", pdf_rows)
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        return await try_put_file(
            connector, ctx, folder_id, f"bind-issuance-{timestamp}.pdf",
            pdf_bytes, "application/pdf",
        )

    @staticmethod
    def _resolve_obligation_due_date(due_date: str | None, anchor: str) -> str | None:
        """``PostBindObligation.due_date`` is a relative offset (``"+30d"``, set by
        ``BindIssuanceEngine._parse_obligation``) — never an absolute date, since
        nothing upstream fixes a bind-approval timestamp at decision time. Resolves
        it against ``anchor`` (the bind's own evaluation timestamp, ``detail.activity[0].at``)
        to a real ``yyyy-mm-dd`` calendar's own point of reference."""
        if not due_date:
            return None
        m = re.match(r"\+(\d+)d$", due_date)
        if not m:
            return None
        anchor_date = datetime.fromisoformat(anchor).date()
        return (anchor_date + timedelta(days=int(m.group(1)))).isoformat()

    async def add_obligation_to_calendar(
        self, session: AsyncSession, ctx: Ctx, submission_id: str, obligation_index: int,
    ) -> str:
        """Creates (or updates) one all-day Google Calendar event for ONE specific
        post-bind obligation on ONE bind order — a per-item, per-obligation action
        (each obligation has its own button in the FE), not a bulk export. Manual,
        button-triggered; never fails the caller: an unconnected Calendar
        integration is a normal, logged skip. The event's id is deterministic
        (derived from the bind id + obligation index) so a repeat click updates
        the same event instead of duplicating it."""
        detail = await self.get_detail(session, ctx, submission_id)
        if detail is None:
            raise KeyError(f"no bind-issuance detail for submission '{submission_id}'")
        if obligation_index < 0 or obligation_index >= len(detail.postBindObligations):
            raise ValueError(
                f"bind '{submission_id}' has no obligation at index {obligation_index}")
        obligation = detail.postBindObligations[obligation_index]
        if not detail.activity:
            return "skipped-no-due-date"
        due = self._resolve_obligation_due_date(obligation.dueDate, detail.activity[0].at)
        if due is None:
            return "skipped-no-due-date"
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_create_event(
            connector, ctx, f"bind-issuance-{submission_id}-obligation-{obligation_index}",
            summary=f"Post-bind obligation: {obligation.description} ({detail.namedInsured})",
            description=(
                f"Bind {submission_id} — {detail.namedInsured}. {obligation.description}. "
                f"Reminders at {list(obligation.reminderDaysBefore)} day(s) before."
            ),
            start_date=due, end_date=due,
        )
