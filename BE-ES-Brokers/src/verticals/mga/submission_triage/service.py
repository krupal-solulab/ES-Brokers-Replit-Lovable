"""Submission Triage pipeline — wires the shared services + the MGA Appetite Engine.

ingest(mock) → extract → validate(shared RulesEngine) → decide(Appetite Engine) →
draft(grounded LLM, suppressed for DECLINE/manual per FR-23) → OutputPackage →
review-queue item → audit entry. Human actions (approve/send/escalate) go through the
shared review queue; nothing auto-sends.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.audit import DefaultAuditService
from core.common.dtos import (
    AuditEntry,
    Citation,
    Ctx,
    Draft,
    ExtractedModel,
    ExtractedValue,
)
from core.common.dtos import (
    OutputPackage as OutputPackageDTO,
)
from core.common.enums import DecisionOutcome, ReviewAction
from core.config import get_settings
from core.extraction import DefaultExtractionService
from core.extraction.service import coerce_number
from core.ingestion import (
    build_connector_service,
    resolve_drive_folder_id,
    resolve_sheet_id,
    try_append_rows,
    try_put_file,
)
from core.ingestion.pdf_export import render_bulk_summary_pdf
from core.llm import build_llm_service
from core.models import (
    Decision as DecisionRow,
)
from core.models import (
    OutputPackage as OutputPackageRow,
)
from core.models import (
    ReviewItem as ReviewItemRow,
)
from core.models import (
    Submission,
)
from core.review_queue import DefaultReviewQueueService
from verticals.mga.decision_core import AppetiteEngine
from verticals.mga.decision_core.broker_contact import parse_broker_from_email
from verticals.mga.models import MgaAppetiteResult
from verticals.mga.rulesets import VALIDATION_KEY, ensure_ruleset, load_ruleset_json
from verticals.mga.submission_triage.schema import (
    ActivityEntry,
    AppetiteResultOut,
    ConsistencyCheck,
    ExtractedFieldOut,
    InboxRow,
    LossMetrics,
    MissingItem,
    RiskFactor,
    SubmissionRow,
    TriageBroker,
    TriageDetail,
    TriageDoc,
    TriageMeta,
)

WORKFLOW = "submission-triage"
RULES_VERSION = f"{VALIDATION_KEY} v1"
_SHEET_TAB = "Submission Triage"
_SHEET_HEADER = [
    "ID", "Subject", "Insured", "Industry", "State", "TIV", "Premium",
    "Score", "Appetite", "Recommendation", "Status", "Received",
]

_ACTIONS = {
    "approve": ReviewAction.APPROVE,
    "send": ReviewAction.SEND,       # human-triggered request-info to broker (no auto-send)
    "escalate": ReviewAction.ESCALATE,
}
# facts (with citations) handed to the grounded LLM narrative
_NARRATIVE_FIELDS = (
    "acord.named_insured", "acord.class_code", "acord.stated_annual_revenue",
    "acord.states_of_operation", "loss_run.total_incurred", "financials.total_revenue",
)
_APPETITE_LABEL = {
    DecisionOutcome.PROCEED: "In appetite",
    DecisionOutcome.REQUEST_INFO: "Needs info",
    DecisionOutcome.DECLINE: "Out of appetite",
}


def _fmt_money(value: Any) -> str:
    n = coerce_number(value)
    return f"${n:,.0f}" if n is not None else (str(value) if value not in (None, "") else "—")


def _humanize(leaf: str) -> str:
    return leaf.split(".", 1)[-1].replace("_", " ").title()


def _parse_years(period: Any) -> int:
    m = re.match(r"(\d+)", str(period or ""))
    return int(m.group(1)) if m else 0


def _cite_str(c: Citation | None) -> str | None:
    if c is None:
        return None
    return f"{c.filename}:{c.locator}" if c.locator else c.filename


class TriageService:
    def __init__(self, workflow_n: int = 1) -> None:
        self.workflow_n = workflow_n
        self.extraction = DefaultExtractionService()
        self.appetite = AppetiteEngine()
        self.llm = build_llm_service()
        self.review_queue = DefaultReviewQueueService()
        self.audit = DefaultAuditService()

    # ── run the pipeline for one submission ─────────
    async def triage(self, session: AsyncSession, ctx: Ctx, message_id: str) -> TriageDetail:
        connector = build_connector_service(
            workflow_n=self.workflow_n, session=session, tenant_id=ctx.tenant_id
        )
        raw = await connector.to_raw_bundle(ctx, message_id)

        sub = Submission(tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                         external_ref=message_id, subject=raw.email_subject or message_id,
                         status="triaged")
        session.add(sub)
        await session.flush()

        model = await self.extraction.extract(ctx, raw)

        engine = await ensure_ruleset(session, ctx)
        rule_results = await engine.evaluate(session, ctx, VALIDATION_KEY, model)
        decision = self.appetite.decide(model, rule_results)

        narrative, citations = await self._narrative(ctx, model, decision)
        detail = self._build_detail(sub.id, model, raw, decision, narrative, citations)

        now = datetime.now(UTC).isoformat()
        detail.activity = [ActivityEntry(
            at=now, who="system (AI)",
            what=f"Auto-triaged -> {decision.outcome.value}",
            conf=f"{detail.confidence:.0%}")]
        row = self._build_row(sub.id, model, decision, detail)

        session.add(DecisionRow(
            tenant_id=ctx.tenant_id, submission_id=sub.id, outcome=decision.outcome,
            score=decision.score, rationale=decision.rationale, details=decision.details))
        session.add(MgaAppetiteResult(
            tenant_id=ctx.tenant_id, submission_id=sub.id, outcome=decision.outcome.value,
            score=decision.score, triggered_rule_ids=list(decision.details.get("failed_rules", [])),
            flags=list(decision.details.get("flags", []))))

        out_dto = OutputPackageDTO(
            submission_id=sub.id, decision=decision,
            draft=Draft(text=narrative, citations=[]),
            flags=list(decision.details.get("flags", [])),
            missing_info=[m["item"] for m in decision.details.get("missing_info", [])],
            payload={"detail": detail.model_dump(by_alias=True), "row": row.model_dump(),
                     "activity": [a.model_dump() for a in detail.activity]})
        await self.review_queue.enqueue(session, ctx, out_dto, WORKFLOW)

        await self.audit.record(session, ctx, AuditEntry(
            actor="ai", who="system", what=f"Triage recommendation: {decision.outcome.value}",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"submission": message_id, "score": decision.score}))
        await session.commit()
        return detail

    # ── narrative (grounded; suppressed for DECLINE / manual review) ──
    async def _narrative(
        self, ctx: Ctx, model: ExtractedModel, decision: Any
    ) -> tuple[str, list[str]]:
        if decision.details.get("suppress_narrative"):
            if decision.details.get("manual_review"):
                return ("Routed to manual review — extraction confidence below threshold; "
                        "automated triage suppressed on degraded input."), []
            return (f"Declined on hard rule(s): {decision.rationale} "
                    "Narrative suppressed pending underwriter confirmation."), []

        by_name = {f.name: f for f in model.fields}
        facts = [by_name[n] for n in _NARRATIVE_FIELDS if n in by_name]
        draft = await self.llm.draft(
            ctx, "Write a concise 2-3 sentence underwriting triage summary using only these facts.",
            facts, tier="standard")
        return draft.text, [s for c in draft.citations if (s := _cite_str(c))]

    # ── assemble the FE TriageDetail ────────────────
    def _build_detail(
        self, sub_id: str, model: ExtractedModel, raw: Any, decision: Any,
        narrative: str, citations: list[str],
    ) -> TriageDetail:
        d = decision.details
        by_name: dict[str, ExtractedValue] = {f.name: f for f in model.fields}
        required_fields = self._required_fields()
        by_value = {f.name: str(f.value) for f in model.fields}
        broker_contact = parse_broker_from_email(raw.email_from, by_value.get("email.from", ""))

        # docs
        present_kinds = [n.split(".")[1] for n in by_name if n.startswith("documents.")]
        docs: list[TriageDoc] = []
        for doc in raw.documents:
            kind = doc.kind.value
            doc_fields = [f for f in model.fields
                          if f.citation is not None and f.citation.filename == doc.filename]
            conf = min((f.confidence for f in doc_fields if f.confidence is not None), default=1.0)
            docs.append(TriageDoc(name=doc.filename, kind=kind, pages=1,
                                  fields=len(doc_fields), confidence=conf, classified=True))

        # extracted scalar fields
        fields_out: list[ExtractedFieldOut] = []
        for f in model.fields:
            if f.name.startswith("documents.") or isinstance(f.value, list):
                continue
            fields_out.append(ExtractedFieldOut(
                key=f.name, label=_humanize(f.name),
                value=None if f.value is None else str(f.value),
                required=f.name in required_fields,
                confidence=f.confidence if f.confidence is not None else 1.0,
                source=_cite_str(f.citation)))

        loss = LossMetrics(
            totalIncurred=_fmt_money(by_name.get("loss_run.total_incurred", _empty()).value),
            totalPaid=_fmt_money(by_name.get("loss_run.total_paid", _empty()).value),
            openClaims=int(coerce_number(by_name.get("loss_run.open_claims", _empty()).value) or 0),
            years=_parse_years(by_name.get("loss_run.total_incurred_period", _empty()).value),
            required=self.appetite.cfg.min_loss_years,
            trend=str(d.get("trend", "flat")))

        return TriageDetail(
            id=sub_id,
            subject=raw.email_subject or sub_id,
            recommendation=decision.outcome.value,
            confidence=float(d.get("extraction_confidence", 1.0)),
            hardRulePassed=bool(d.get("hard_rule_passed", True)),
            failedRules=list(d.get("failed_rules", [])),
            processing="ready",
            rulesVersion=RULES_VERSION,
            meta=TriageMeta(received=sorted(present_kinds),
                            lowConfidence=list(d.get("low_confidence_fields", [])),
                            timestamp=datetime.now(UTC).isoformat()),
            docs=docs,
            fields=fields_out,
            loss=loss,
            consistency=[ConsistencyCheck(**c) for c in d.get("consistency", [])],
            missingInfo=[MissingItem(**m) for m in d.get("missing_info", [])],
            factors=[RiskFactor(name=f["name"], value=str(f["value"]), weight=int(f["weight"]))
                     for f in d.get("factors", [])],
            narrative=narrative,
            citations=citations,
            appetite=[AppetiteResultOut(rule=a["rule"], passed=a["pass"], hard=a["hard"],
                                        detail=a["detail"]) for a in d.get("appetite", [])],
            activity=[],
            broker=(TriageBroker(name=broker_contact.name, agency=broker_contact.agency,
                                 tenure=broker_contact.tenure, note=broker_contact.note,
                                 email=broker_contact.email)
                   if broker_contact.email else None))

    # Known label variants that normalize to a different field key than the mock
    # fixtures use (e.g. "Total Insurable Value (TIV)" -> total_insurable_value_tiv,
    # "Prior Annual Premium" -> prior_annual_premium) — real submission emails don't
    # always match the fixtures' exact wording, so the summary row checks aliases
    # rather than silently showing a placeholder when the value was actually extracted.
    _TIV_KEYS = ("sov.total_insurable_value", "acord.total_insurable_value_tiv", "acord.total_insurable_value")
    _PREMIUM_KEYS = ("acord.prior_premium", "acord.prior_annual_premium",
                     "financials.prior_premium", "financials.prior_annual_premium")
    # A plain-text submission email rarely says the word "ACORD" — which DocumentKind
    # wins the content-signal classification (acord vs. financials) is an accident of
    # phrasing (e.g. "Stated Annual Revenue" alone trips the financials signal), not
    # something the row builder should assume. Check every kind a name/class/state/
    # revenue label might have landed under, not just "acord.".
    _INSURED_KEYS = ("acord.named_insured", "financials.named_insured")
    _CLASS_CODE_KEYS = ("acord.class_code", "financials.class_code")
    _STATE_KEYS = ("acord.states_of_operation", "financials.states_of_operation")

    @staticmethod
    def _first_present(by_name: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if by_name.get(key) is not None:
                return by_name[key]
        return None

    def _build_row(
        self, sub_id: str, model: ExtractedModel, decision: Any, detail: TriageDetail
    ) -> SubmissionRow:
        by_name = {f.name: f.value for f in model.fields}
        class_code = str(self._first_present(by_name, self._CLASS_CODE_KEYS) or "")
        industry = class_code.split(" - ", 1)[-1] if " - " in class_code else (class_code or "—")
        return SubmissionRow(
            id=sub_id,
            subject=detail.subject,
            insured=str(self._first_present(by_name, self._INSURED_KEYS) or "—"),
            industry=industry,
            state=str(self._first_present(by_name, self._STATE_KEYS) or "—"),
            tiv=_fmt_money(self._first_present(by_name, self._TIV_KEYS)),
            premium=_fmt_money(self._first_present(by_name, self._PREMIUM_KEYS)),
            score=int(decision.score) if decision.score is not None else None,
            appetite=_APPETITE_LABEL[decision.outcome],
            recommendation=decision.outcome.value,
            status="pending",
            received=str(by_name.get("email.date") or detail.meta.timestamp))

    @staticmethod
    def _required_fields() -> set[str]:
        rs = load_ruleset_json("workflow1_validation")
        return {r["field"] for r in rs.get("rules", []) if r.get("check") == "required"}

    # ── live inbox (unfiltered mailbox, mock or live per CONNECTORS_MODE) ──
    async def list_inbox(self, session: AsyncSession, ctx: Ctx) -> list[InboxRow]:
        connector = build_connector_service(
            workflow_n=self.workflow_n, session=session, tenant_id=ctx.tenant_id
        )
        messages = await connector.fetch_inbox(ctx)

        refs = [m.id for m in messages]
        triaged_refs: set[str] = set()
        if refs:
            # Scoped to status="triaged" (this workflow's own marker) — Submission rows
            # are shared across MGA workflows keyed by external_ref, so an unscoped
            # lookup would wrongly report a message as triaged just because Renewal
            # Management (status="renewal") had already processed the same message.
            stmt = select(Submission.external_ref).where(
                col(Submission.tenant_id) == ctx.tenant_id,
                col(Submission.external_ref).in_(refs),
                col(Submission.status) == "triaged",
            )
            triaged_refs = {r for r in (await session.execute(stmt)).scalars().all() if r}

        return [
            InboxRow(id=m.id, subject=m.subject, triaged=m.id in triaged_refs)
            for m in messages
        ]

    # ── list / detail / act ─────────────────────────
    async def list_rows(self, session: AsyncSession, ctx: Ctx) -> list[SubmissionRow]:
        stmt = (select(ReviewItemRow, OutputPackageRow)
                .join(OutputPackageRow,
                      col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
                .where(col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                       col(ReviewItemRow.workflow) == WORKFLOW))
        rows: list[SubmissionRow] = []
        for item, pkg in (await session.execute(stmt)).all():
            payload = pkg.payload or {}
            row_payload = payload["row"]
            row = SubmissionRow(**{"subject": row_payload.get("id", ""), **row_payload})
            row.status = item.status.value if hasattr(item.status, "value") else str(item.status)
            rows.append(row)
        return rows

    async def get_detail(
        self, session: AsyncSession, ctx: Ctx, submission_id: str
    ) -> TriageDetail | None:
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
        detail_payload = {"id": submission_id, "subject": submission_id,
                          "reviewStatus": review_status, **pkg.payload["detail"]}
        return TriageDetail.model_validate(detail_payload)

    async def act(
        self, session: AsyncSession, ctx: Ctx, submission_id: str, action: str,
        amount: float | None = None, note: str | None = None,
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
            raise KeyError(f"no review item for submission '{submission_id}'")
        result = await self.review_queue.act(session, ctx, item.id, review_action, amount)
        # `note` is Appetite Governance's AG-04 override-reason input — a human's stated
        # reason for overriding the AI's recommendation, when they give one. Stored on
        # AuditEntry.detail (already-JSON, already the record of this exact action) so a
        # governance query can read it back per submission with no new column.
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
        """Exports every submission currently in this tenant's list — regardless
        of review status — as one row each into the shared spreadsheet's
        "Submission Triage" tab. Manual, button-triggered; never fails the caller."""
        sheet_id = await resolve_sheet_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        sheet_rows = [
            [
                r.id, r.subject, r.insured, r.industry, r.state, r.tiv, r.premium,
                r.score, r.appetite, r.recommendation, r.status, r.received,
            ]
            for r in rows
        ]
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_append_rows(
            connector, ctx, sheet_id, sheet_rows, tab=_SHEET_TAB, header=_SHEET_HEADER
        )

    async def export_all_to_drive(self, session: AsyncSession, ctx: Ctx) -> str:
        """Generates one PDF (one page per submission currently in this tenant's
        list, regardless of review status) and uploads it to the tenant's
        connected Drive. Manual, button-triggered."""
        folder_id = await resolve_drive_folder_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        pdf_rows = [
            [
                ("ID", r.id), ("Subject", r.subject), ("Insured", r.insured),
                ("Industry", r.industry), ("State", r.state), ("TIV", r.tiv),
                ("Premium", r.premium), ("Score", str(r.score)),
                ("Appetite", r.appetite), ("Recommendation", r.recommendation),
                ("Status", r.status), ("Received", r.received),
            ]
            for r in rows
        ]
        pdf_bytes = render_bulk_summary_pdf("Submission Triage", pdf_rows)
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        return await try_put_file(
            connector, ctx, folder_id, f"submission-triage-{timestamp}.pdf",
            pdf_bytes, "application/pdf",
        )


def _empty() -> ExtractedValue:
    return ExtractedValue(name="_", value=None)
