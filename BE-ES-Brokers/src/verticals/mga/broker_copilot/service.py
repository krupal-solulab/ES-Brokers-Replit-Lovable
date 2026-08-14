"""Broker Communication Copilot pipeline — read(existing Triage/Renewal OutputPackage) →
classify trigger → calibrate tone (Decision Core reuse) → LLM(grounded, cited) →
OutputPackage → review → audit. No new extraction/ingestion: every draft is generated
FROM a decision already produced by Submission Triage or Renewal Management (roadmap
"Reuses Extraction Core: High" / "Reuses Decision Core: Medium"). Nothing sends
automatically — a real Gmail send only happens when a human explicitly triggers the
"send" action via `act()`, and only once a real recipient email is on file.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.audit import DefaultAuditService
from core.common.dtos import AuditEntry, Citation, Ctx, Draft, ExtractedValue
from core.common.dtos import Decision as DecisionDTO
from core.common.dtos import OutputPackage as OutputPackageDTO
from core.common.enums import DecisionOutcome, DocumentKind, ReviewAction
from core.config import get_settings
from core.ingestion import (
    build_connector_service,
    resolve_drive_folder_id,
    resolve_sheet_id,
    try_append_rows,
    try_put_file,
)
from core.ingestion.pdf_export import render_bulk_summary_pdf
from core.llm import build_llm_service
from core.models import Decision as DecisionRow
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.models import Submission
from core.review_queue import DefaultReviewQueueService
from verticals.mga.broker_copilot import fixtures as trigger_fixtures
from verticals.mga.broker_copilot.drafting import BrokerDraftingEngine, BrokerRelationship
from verticals.mga.broker_copilot.schema import (
    ActivityEntry,
    BrokerContext,
    CommCitation,
    CommDraft,
)
from verticals.mga.models import MgaBrokerCommResult

WORKFLOW = "broker-copilot"
_SHEET_TAB = "Broker Copilot"
_SHEET_HEADER = [
    "Draft ID", "Source Workflow", "Named Insured", "Subject", "Type", "Status",
]

_SOURCE_WORKFLOWS = {
    "submission-triage": "Submission Triage",
    "renewal-management": "Renewal Management",
    "endorsement-processing": "Endorsement Processing",
}
_SOURCE_ROUTE = {
    "submission-triage": "/app/workflows/submission-triage",
    "renewal-management": "/app/workflows/renewal-management",
    "endorsement-processing": "/app/workflows/endorsements",
}

_ACTIONS = {
    "approve": ReviewAction.APPROVE,
    "send": ReviewAction.SEND,       # human-triggered broker send (no auto-send)
    "escalate": ReviewAction.ESCALATE,
}


def _cite_str(c: Citation | None) -> str | None:
    if c is None:
        return None
    return f"{c.filename}:{c.locator}" if c.locator else c.filename


def _broker_from_detail(detail: dict[str, Any]) -> BrokerRelationship:
    """Every source workflow detail carries a ``broker`` block (Triage's narrative facts
    or Renewal's ``RenewalBroker``) — fall back to an unknown/neutral relationship if not.

    Never fabricates an email address (PRD FR-4/FR-7: no fabricated specifics) — if the
    real sender's email isn't available on the source record, this stays empty and the
    caller/UI must show that honestly rather than a plausible-looking placeholder."""
    b = detail.get("broker") or {}
    name = str(b.get("name") or "—")
    agency = str(b.get("agency") or "—")
    email = str(b.get("email") or "")
    tenure = b.get("tenureYears") if isinstance(b.get("tenureYears"), int) else None
    tier = b.get("volumeTier") if isinstance(b.get("volumeTier"), str) else None
    return BrokerRelationship(name=name, agency=agency, email=email,
                              tenure_years=tenure, volume_tier=tier)


class BrokerCopilotService:
    def __init__(self) -> None:
        self.engine = BrokerDraftingEngine()
        self.llm = build_llm_service()
        self.review_queue = DefaultReviewQueueService()
        self.audit = DefaultAuditService()

    async def _load_source(
        self, session: AsyncSession, ctx: Ctx, source_workflow: str, submission_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], DecisionOutcome, dict[str, Any], str]:
        """Read back the source workflow's persisted OutputPackage + Decision.

        Returns (detail, row, outcome, decision_details, resolved_submission_id) —
        ``row`` carries ``insured`` for Triage/Endorsement (not present on their own
        ``*Detail`` types); ``detail`` carries ``broker`` for Renewal (Endorsement has
        no broker block — ``_broker_from_detail`` falls back to unknown, never
        fabricated). Reading both keeps this workflow-shape-agnostic across sources
        without touching any source workflow's schema.
        ``resolved_submission_id`` is normally just ``submission_id`` unchanged; the
        fixture fallback path (Triage/Renewal only — Endorsement has no fixture
        trigger set, since its real DB path always exists once it has run at all)
        returns a freshly created ``Submission`` row's real id instead, since every
        downstream table (``OutputPackage``, ``MgaBrokerCommResult``, ``ReviewItem``)
        has ``submission_id`` as a real foreign key — a fixture's own id (e.g.
        "SUB-2210") was never a row in that table.
        """
        pkg = (await session.execute(
            select(OutputPackageRow).where(
                col(OutputPackageRow.tenant_id) == ctx.tenant_id,
                col(OutputPackageRow.submission_id) == submission_id,
                col(OutputPackageRow.workflow) == source_workflow))
        ).scalars().first()
        if pkg is None or not pkg.payload:
            # No real Triage/Renewal decision persisted yet — fall back to the
            # Workflow-03 sample dataset (mirrors CONNECTORS_MODE=mock for the two
            # upstream workflows: same shape, fixture-backed instead of DB-backed).
            trigger = trigger_fixtures.find_trigger_by_id(submission_id)
            if trigger is None:
                raise KeyError(f"no {source_workflow} output for submission '{submission_id}'")
            detail, row, outcome, decision_details = trigger_fixtures.as_source(trigger)
            sub = Submission(tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                             external_ref=submission_id, subject=submission_id,
                             status="broker-comm-fixture")
            session.add(sub)
            await session.flush()
            return detail, row, outcome, decision_details, sub.id
        decision_row = (await session.execute(
            select(DecisionRow).where(
                col(DecisionRow.tenant_id) == ctx.tenant_id,
                col(DecisionRow.submission_id) == submission_id))
        ).scalars().first()
        outcome = decision_row.outcome if decision_row is not None else DecisionOutcome.PROCEED
        details = decision_row.details if decision_row is not None else {}
        return pkg.payload["detail"], pkg.payload.get("row", {}), outcome, details, submission_id

    async def _find_existing_draft(
        self, session: AsyncSession, ctx: Ctx, source_workflow: str, submission_id: str,
    ) -> CommDraft | None:
        """Idempotency guard: a repeated "Draft to broker" click for the same source
        decision must reuse the existing draft, not create a duplicate — this is what
        previously inflated the draft queue count on every repeat click. Resolves
        ``submission_id`` the same way ``_load_source`` does for the fixture-fallback
        case (its own fresh ``Submission.external_ref`` lookup) before checking for an
        existing broker-copilot ``OutputPackageRow``, so a fixture-backed trigger id
        (e.g. "SUB-2210") is matched correctly even though its resolved real id differs
        from the id passed in here."""
        resolved_id = submission_id
        pkg_exists = (await session.execute(
            select(OutputPackageRow.submission_id).where(
                col(OutputPackageRow.tenant_id) == ctx.tenant_id,
                col(OutputPackageRow.submission_id) == submission_id,
                col(OutputPackageRow.workflow) == source_workflow))
        ).scalars().first()
        if pkg_exists is None:
            # Not a real Triage/Renewal decision id — check whether a fixture
            # Submission was already created for this trigger id on a prior call.
            fixture_sub_id = (await session.execute(
                select(Submission.id).where(
                    col(Submission.tenant_id) == ctx.tenant_id,
                    col(Submission.external_ref) == submission_id,
                    col(Submission.status) == "broker-comm-fixture"))
            ).scalars().first()
            if fixture_sub_id is None:
                return None
            resolved_id = fixture_sub_id

        existing = (await session.execute(
            select(ReviewItemRow.submission_id).where(
                col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                col(ReviewItemRow.submission_id) == resolved_id,
                col(ReviewItemRow.workflow) == WORKFLOW))
        ).scalars().first()
        if existing is None:
            return None
        return await self.get_detail(session, ctx, f"DRF-{existing[-6:] if len(existing) >= 6 else existing}")

    async def draft(
        self, session: AsyncSession, ctx: Ctx, source_workflow: str, submission_id: str,
    ) -> CommDraft:
        existing_draft = await self._find_existing_draft(session, ctx, source_workflow, submission_id)
        if existing_draft is not None:
            return existing_draft

        detail, row, outcome, details, submission_id = await self._load_source(
            session, ctx, source_workflow, submission_id)

        comm_type = self.engine.classify(source_workflow, outcome, details)
        broker = _broker_from_detail(detail)
        plan = self.engine.calibrate_tone(
            comm_type, broker, details.get("days_until_effective_date"))
        named_insured = str(row.get("insured") or detail.get("broker", {}).get("name") or "—")
        subject = self.engine.subject_for(comm_type, named_insured, source_workflow)

        facts = self._facts(detail)
        llm_draft = await self.llm.draft(
            ctx, self.engine.instruction_for(comm_type, plan.tone), facts, tier="standard")
        citations = [CommCitation(claim=f.name, source=_cite_str(f.citation) or "—")
                     for f in facts if f.citation is not None]

        now = datetime.now(UTC).isoformat()
        draft_id = f"DRF-{submission_id[-6:] if len(submission_id) >= 6 else submission_id}"
        comm = CommDraft(
            id=draft_id, type=comm_type,
            sourceWorkflow=_SOURCE_WORKFLOWS[source_workflow], sourceId=submission_id,
            sourceRoute=_SOURCE_ROUTE[source_workflow], namedInsured=named_insured,
            broker=BrokerContext(name=broker.name, agency=broker.agency, email=broker.email,
                                 tenureYears=broker.tenure_years, volumeTier=broker.volume_tier),
            subject=subject, tone=plan.tone, toneWhy=plan.tone_why, sensitive=plan.sensitive,
            requiresComplianceReview=plan.requires_compliance_review, combined=plan.combined,
            deadlineRef=plan.deadline_ref, citations=citations, body=llm_draft.text,
            status="UNDER_COMPLIANCE_REVIEW" if plan.requires_compliance_review else "DRAFT",
            generatedAt=now,
            activity=[ActivityEntry(at=now, who="AI · Decision Core",
                                    what=f"Drafted {comm_type.replace('_', ' ').title()}",
                                    ctx=f"from {submission_id}", conf="—")],
        )

        session.add(MgaBrokerCommResult(
            tenant_id=ctx.tenant_id, submission_id=submission_id,
            source_workflow=source_workflow, comm_type=comm_type, tone=plan.tone,
            requires_compliance_review=plan.requires_compliance_review, sensitive=plan.sensitive))

        out_dto = OutputPackageDTO(
            submission_id=submission_id,
            decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None,
                                 rationale=f"Broker communication drafted: {comm_type}"),
            draft=Draft(text=comm.body, citations=llm_draft.citations),
            flags=[comm_type], missing_info=[],
            payload={"detail": comm.model_dump(by_alias=True)},
        )
        await self.review_queue.enqueue(session, ctx, out_dto, WORKFLOW)

        await self.audit.record(session, ctx, AuditEntry(
            actor="ai", who="system", what=f"Broker draft generated: {comm_type}",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"submission": submission_id, "type": comm_type}))
        await session.commit()
        return comm

    @staticmethod
    def _facts(detail: dict[str, Any]) -> list[ExtractedValue]:
        """Reassemble cited facts from the source detail's own narrative/citations —
        no re-extraction, per the roadmap's 'High Extraction Core reuse' rating."""
        facts: list[ExtractedValue] = []
        narrative = detail.get("narrative")
        if narrative:
            facts.append(ExtractedValue(name="source.narrative", value=narrative))
        for item in detail.get("missingInfo", []) or []:
            facts.append(ExtractedValue(
                name=f"missing.{item.get('item', 'item')}", value=item.get("reason", "")))
        for c in detail.get("consistency", []) or []:
            if c.get("status") in ("warn", "fail"):
                facts.append(ExtractedValue(name=f"consistency.{c.get('label', 'check')}",
                                            value=c.get("detail", "")))
        for f in detail.get("changes", []) or []:
            facts.append(ExtractedValue(name=f"change.{f.get('item', 'item')}",
                                        value=f.get("reason", ""),
                                        citation=Citation(document_kind=DocumentKind.OTHER,
                                                          filename=str(f.get("source") or "decision"))))
        return facts

    # ── list / detail / act ──
    async def list_drafts(self, session: AsyncSession, ctx: Ctx) -> list[CommDraft]:
        stmt = (select(ReviewItemRow, OutputPackageRow)
                .join(OutputPackageRow,
                      col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
                .where(col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                       col(ReviewItemRow.workflow) == WORKFLOW))
        drafts: list[CommDraft] = []
        for item, pkg in (await session.execute(stmt)).all():
            payload = pkg.payload or {}
            if "detail" not in payload:
                continue
            comm = CommDraft.model_validate(payload["detail"])
            comm.status = item.status.value if hasattr(item.status, "value") else str(item.status)
            drafts.append(comm)
        return drafts

    async def get_detail(
        self, session: AsyncSession, ctx: Ctx, draft_id: str
    ) -> CommDraft | None:
        for comm in await self.list_drafts(session, ctx):
            if comm.id == draft_id:
                return comm
        return None

    async def act(
        self, session: AsyncSession, ctx: Ctx, submission_id: str, action: str,
        body: str | None = None,
    ) -> dict[str, str]:
        review_action = _ACTIONS.get(action)
        if review_action is None:
            raise ValueError(f"unknown action '{action}'; allowed: {sorted(_ACTIONS)}")
        row = (await session.execute(
            select(ReviewItemRow, OutputPackageRow)
            .join(OutputPackageRow,
                  col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
            .where(col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                   col(ReviewItemRow.submission_id) == submission_id,
                   col(ReviewItemRow.workflow) == WORKFLOW))
        ).first()
        if row is None:
            raise KeyError(f"no broker-copilot review item for submission '{submission_id}'")
        item, pkg = row

        audit_detail: dict[str, Any] = {"submission": submission_id, "action": action,
                                        "edited": body is not None}
        if action == "send":
            # The one real outbound case in this vertical — every other workflow's
            # "send" only ever flips a review-queue status. Never mark a draft SENT
            # before the real dispatch actually succeeds.
            draft_payload = (pkg.payload or {}).get("detail", {})
            to_email = str((draft_payload.get("broker") or {}).get("email") or "")
            if not to_email:
                raise ValueError(
                    f"no recipient email on file for submission '{submission_id}' — "
                    "cannot send. The source Triage/Renewal decision never captured a "
                    "real broker email for this draft.")
            connector = build_connector_service(
                workflow_n=3, session=session, tenant_id=ctx.tenant_id)
            sent = await connector.send_email(ctx, {
                "to": to_email,
                "subject": str(draft_payload.get("subject") or ""),
                "body": body if body is not None else str(draft_payload.get("body") or ""),
            })
            audit_detail["sent_to"] = sent.to
            audit_detail["thread_id"] = sent.thread_id

        result = await self.review_queue.act(session, ctx, item.id, review_action)
        await self.audit.record(session, ctx, AuditEntry(
            actor="human", who=ctx.user_id, what=f"{action} (role={ctx.role.value})",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail=audit_detail))
        await session.commit()
        return {"id": result.id, "status": result.status.value}

    async def export_all_to_sheet(self, session: AsyncSession, ctx: Ctx) -> str:
        """Exports every draft currently in this tenant's queue — regardless of
        review status — as one row each into the shared spreadsheet's "Broker
        Copilot" tab. Manual, button-triggered; never fails the caller. Uses
        ``list_drafts`` (this workflow's own name for its list method — see
        docs/CONNECTORS_NANGO.md)."""
        sheet_id = await resolve_sheet_id(session, ctx.tenant_id, get_settings())
        drafts = await self.list_drafts(session, ctx)
        sheet_rows = [
            [d.id, d.sourceWorkflow, d.namedInsured, d.subject, d.type, d.status]
            for d in drafts
        ]
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_append_rows(
            connector, ctx, sheet_id, sheet_rows, tab=_SHEET_TAB, header=_SHEET_HEADER
        )

    async def export_all_to_drive(self, session: AsyncSession, ctx: Ctx) -> str:
        """Generates one PDF (one page per draft currently in this tenant's queue,
        regardless of review status) and uploads it to the tenant's connected
        Drive. Manual, button-triggered."""
        folder_id = await resolve_drive_folder_id(session, ctx.tenant_id, get_settings())
        drafts = await self.list_drafts(session, ctx)
        pdf_rows = [
            [
                ("Draft ID", d.id), ("Source Workflow", d.sourceWorkflow),
                ("Named Insured", d.namedInsured), ("Subject", d.subject),
                ("Type", d.type), ("Status", d.status),
            ]
            for d in drafts
        ]
        pdf_bytes = render_bulk_summary_pdf("Broker Copilot", pdf_rows)
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        return await try_put_file(
            connector, ctx, folder_id, f"broker-copilot-{timestamp}.pdf",
            pdf_bytes, "application/pdf",
        )
