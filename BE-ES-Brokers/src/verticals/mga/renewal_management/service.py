"""Renewal Management pipeline — ingest(mock) → extract → rules(published) → compare →
LLM(grounded, cited) → OutputPackage → review → audit. Maps the frozen ``Decision`` onto
the FE ``RenewalRecommendation`` here (never in core/common). No auto-send.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
)
from core.common.dtos import (
    OutputPackage as OutputPackageDTO,
)
from core.common.enums import DecisionOutcome, ReviewAction
from core.config import get_settings
from core.extraction.service import coerce_number
from core.ingestion import (
    build_connector_service,
    resolve_drive_folder_id,
    resolve_sheet_id,
    try_append_rows,
    try_create_event,
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
from verticals.mga.decision_core.broker_contact import parse_broker_from_email
from verticals.mga.models import MgaRenewalResult
from verticals.mga.renewal_management.comparison import RenewalComparisonEngine
from verticals.mga.renewal_management.extraction import RenewalExtractionService
from verticals.mga.renewal_management.rulesets import VALIDATION_KEY, ensure_ruleset
from verticals.mga.renewal_management.schema import (
    ActivityEntry,
    AppetiteResultOut,
    ChangeFlag,
    CompareRow,
    InboxRow,
    LossChange,
    RenewalBroker,
    RenewalChangeItem,
    RenewalDetail,
    RenewalRow,
    RenewalTiming,
)

WORKFLOW = "renewal-management"
RULES_VERSION = f"{VALIDATION_KEY} v1"
_SHEET_TAB = "Renewal Management"
_SHEET_HEADER = [
    "Renewal ID", "Subject", "Recommendation", "Retention", "Prior Premium",
    "Indicated", "Status",
]

_ACTIONS = {
    "approve": ReviewAction.APPROVE,
    "send": ReviewAction.SEND,       # human-triggered broker outreach (no auto-send)
    "escalate": ReviewAction.ESCALATE,
}
_NARRATIVE_FIELDS = (
    "prior_policy.named_insured", "prior_policy.class_code",
    "prior_policy.stated_revenue_at_prior_renewal",
    "renewal_questionnaire.stated_current_annual_revenue",
    "loss_run.total_incurred", "loss_run.loss_frequency_trend",
)


def _cite_str(c: Citation | None) -> str | None:
    if c is None:
        return None
    return f"{c.filename}:{c.locator}" if c.locator else c.filename


def _premium_metrics(model: ExtractedModel) -> dict[str, str]:
    """Premium + 5yr loss-ratio for the FE, from already-extracted fields.
    priorPremium ← prior_policy.expiring_premium; lossRatio ← 5yr incurred / (prior premium ×5).
    indicated + change stay GAPs ("—") until the workflow computes a re-rate."""
    by = {f.name: f.value for f in model.fields}
    prior = coerce_number(by.get("prior_policy.expiring_premium"))
    incurred = coerce_number(by.get("loss_run.total_incurred"))
    prior_s = f"${prior:,.0f}" if prior is not None else "—"
    loss_ratio = (
        f"{incurred / (prior * 5):.0%}" if prior and incurred is not None else "—"
    )
    return {"priorPremium": prior_s, "indicated": "—", "change": "—", "lossRatio": loss_ratio}


def _broker_from_email(model: ExtractedModel, email_from: str | None = None) -> RenewalBroker:
    """Thin wrapper over the shared ``parse_broker_from_email`` (moved to
    ``decision_core.broker_contact`` so Submission Triage reuses the identical
    parsing, not a re-implementation of the same regex)."""
    by = {f.name: str(f.value) for f in model.fields}
    contact = parse_broker_from_email(email_from, by.get("email.from", ""))
    return RenewalBroker(name=contact.name, agency=contact.agency,
                         tenure=contact.tenure, note=contact.note, email=contact.email)


class RenewalService:
    def __init__(self, workflow_n: int = 2) -> None:
        self.workflow_n = workflow_n
        self.extraction = RenewalExtractionService()
        self.engine = RenewalComparisonEngine()
        self.llm = build_llm_service()
        self.review_queue = DefaultReviewQueueService()
        self.audit = DefaultAuditService()

    def _recommendation(self, decision: Any) -> str:
        d = decision.details
        if decision.outcome is DecisionOutcome.DECLINE:
            return "NON_RENEW"
        change_flags = [f for f in d.get("change_flags", []) if f["category"] != "timing"]
        if decision.outcome is DecisionOutcome.REQUEST_INFO or d.get("needs_info"):
            return "RENEW_WITH_CHANGES"  # needsInfo flag carries the request-info state
        return "RENEW_WITH_CHANGES" if change_flags else "RENEW_AS_IS"

    async def renew(self, session: AsyncSession, ctx: Ctx, message_id: str) -> RenewalDetail:
        connector = build_connector_service(
            workflow_n=self.workflow_n, session=session, tenant_id=ctx.tenant_id
        )
        raw = await connector.to_raw_bundle(ctx, message_id)

        sub = Submission(tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                         external_ref=message_id, subject=raw.email_subject or message_id,
                         status="renewal")
        session.add(sub)
        await session.flush()

        model = await self.extraction.extract(ctx, raw)

        engine = await ensure_ruleset(session, ctx)
        rule_results = await engine.evaluate(session, ctx, VALIDATION_KEY, model)
        decision = self.engine.decide(model, rule_results)

        narrative, citations = await self._narrative(ctx, model, decision)
        detail = self._build_detail(sub.id, raw, model, decision, narrative, citations)
        now = datetime.now(UTC).isoformat()
        detail.activity = [ActivityEntry(at=now, who="system (AI)",
                                         what=f"Renewal compared → {detail.recommendation}",
                                         conf=f"{detail.confidence:.0%}")]
        row = self._build_row(sub.id, model, decision, detail)

        session.add(DecisionRow(
            tenant_id=ctx.tenant_id, submission_id=sub.id, outcome=decision.outcome,
            score=decision.score, rationale=decision.rationale, details=decision.details))
        session.add(MgaRenewalResult(
            tenant_id=ctx.tenant_id, submission_id=sub.id, recommendation=detail.recommendation,
            outcome=decision.outcome.value, score=decision.score,
            retention=decision.details.get("retention"),
            triggered_rule_ids=list(decision.details.get("triggered_rules", [])),
            change_flags=list(decision.details.get("change_flags", []))))

        out_dto = OutputPackageDTO(
            submission_id=sub.id, decision=decision,
            draft=Draft(text=narrative, citations=[]),
            flags=[f["label"] for f in decision.details.get("change_flags", [])],
            missing_info=[m["item"] for m in decision.details.get("missing_info", [])],
            payload={"detail": detail.model_dump(by_alias=True), "row": row.model_dump(),
                     "activity": [a.model_dump() for a in detail.activity]})
        await self.review_queue.enqueue(session, ctx, out_dto, WORKFLOW)
        await self.audit.record(session, ctx, AuditEntry(
            actor="ai", who="system", what=f"Renewal recommendation: {detail.recommendation}",
            workflow=WORKFLOW, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={"submission": message_id, "score": decision.score}))
        await session.commit()
        return detail

    async def _narrative(
        self, ctx: Ctx, model: ExtractedModel, decision: Any
    ) -> tuple[str, list[str]]:
        d = decision.details
        if d.get("manual_review"):
            return ("Routed to manual review — extraction confidence below threshold.", [])
        if decision.outcome is DecisionOutcome.DECLINE:
            return (f"Non-renewal: {decision.rationale} Narrative suppressed pending "
                    "underwriter confirmation and broker-communication framing.", [])
        by_name = {f.name: f for f in model.fields}
        facts = [by_name[n] for n in _NARRATIVE_FIELDS if n in by_name]
        draft = await self.llm.draft(
            ctx, "Write a concise 2-3 sentence renewal summary using only these facts, "
            "noting the direction of any material change.", facts, tier="standard")
        return draft.text, [s for c in draft.citations if (s := _cite_str(c))]

    def _build_detail(
        self, sub_id: str, raw: Any, model: ExtractedModel, decision: Any,
        narrative: str, citations: list[str],
    ) -> RenewalDetail:
        d = decision.details
        rec = self._recommendation(decision)
        drift = d.get("appetite_drift")
        pm = _premium_metrics(model)
        # surface premium as a comparison row too (within the locked CompareRow[] shape)
        comparison = [CompareRow(**c) for c in d.get("comparison", [])]
        if pm["priorPremium"] != "—":
            comparison.insert(0, CompareRow(
                label="Premium", prior=pm["priorPremium"], current=pm["indicated"],
                change=pm["change"], direction="neutral"))
        return RenewalDetail(
            id=sub_id,
            subject=raw.email_subject or sub_id,
            recommendation=rec,
            confidence=float(d.get("extraction_confidence", 1.0)),
            processing="ready",
            priorSource=str(d.get("prior_source", "manual_queue")),
            rulesVersion=RULES_VERSION,
            rulesVersionAtBinding=("appetite @ binding (pre-revision)" if drift else RULES_VERSION),
            hardRulePassed=bool(d.get("hard_rule_passed", True)),
            appetite=[AppetiteResultOut(rule=a["rule"], passed=a["pass"], hard=a["hard"],
                                        detail=a["detail"]) for a in d.get("appetite", [])],
            appetiteDrift=drift,
            comparison=comparison,
            changeFlags=[ChangeFlag(**f) for f in d.get("change_flags", [])],
            lossChanges=[LossChange(**lc) for lc in d.get("loss_changes", [])],
            timing=RenewalTiming(daysToExpiration=int(d.get("days_to_expiration", 0)),
                                 lapseRisk=bool(d.get("lapse_risk")),
                                 noSubmission=bool(d.get("no_submission"))),
            changes=[RenewalChangeItem(**c) for c in d.get("changes", [])],
            narrative=narrative,
            citations=citations,
            broker=_broker_from_email(model, raw.email_from),
            activity=[],
            needsInfo=bool(d.get("needs_info")),
            missingInfo=[RenewalChangeItem(item=m["item"], reason=m["reason"])
                         for m in d.get("missing_info", [])],
            retention=str(d.get("retention", "neutral")),
            priorPremium=pm["priorPremium"], indicated=pm["indicated"],
            premiumChange=pm["change"], lossRatio=pm["lossRatio"],
        )

    def _build_row(
        self, sub_id: str, model: ExtractedModel, decision: Any, detail: RenewalDetail
    ) -> RenewalRow:
        by = {f.name: f.value for f in model.fields}
        return RenewalRow(
            id=sub_id,
            subject=detail.subject,
            insured=str(by.get("prior_policy.named_insured")
                        or by.get("renewal_questionnaire.named_insured")
                        or by.get("acord.named_insured") or "—"),
            recommendation=detail.recommendation,
            score=int(decision.score) if decision.score is not None else None,
            retention=detail.retention,
            daysToExpiration=detail.timing.daysToExpiration,
            lapseRisk=detail.timing.lapseRisk,
            status="pending",
            received=str(by.get("email.date") or datetime.now(UTC).isoformat()),
            priorPremium=detail.priorPremium, indicated=detail.indicated,
            change=detail.premiumChange, lossRatio=detail.lossRatio)

    # ── live inbox (unfiltered mailbox, mock or live per CONNECTORS_MODE) ──
    async def list_inbox(self, session: AsyncSession, ctx: Ctx) -> list[InboxRow]:
        connector = build_connector_service(
            workflow_n=self.workflow_n, session=session, tenant_id=ctx.tenant_id
        )
        # Renewal notices ("Renewal - <Insured> - Eff <date>") don't match Triage's
        # subject:submission search — fetch_inbox's since_cursor param doubles as a
        # full query override on the live connector (ignored by the mock connector),
        # so this workflow gets its own Gmail search instead of sharing Triage's.
        messages = await connector.fetch_inbox(ctx, since_cursor=get_settings().nango_renewal_inbox_query)

        refs = [m.id for m in messages]
        triaged_refs: set[str] = set()
        if refs:
            # Scoped to status="renewal" (this workflow's own marker) — Submission rows
            # are shared across MGA workflows keyed by external_ref, so an unscoped
            # lookup would wrongly report a message as renewed just because Submission
            # Triage (status="triaged") had already processed the same inbox message.
            stmt = select(Submission.external_ref).where(
                col(Submission.tenant_id) == ctx.tenant_id,
                col(Submission.external_ref).in_(refs),
                col(Submission.status) == "renewal",
            )
            triaged_refs = {r for r in (await session.execute(stmt)).scalars().all() if r}

        return [
            InboxRow(id=m.id, subject=m.subject, triaged=m.id in triaged_refs)
            for m in messages
        ]

    # ── list / detail / act ──
    async def list_rows(self, session: AsyncSession, ctx: Ctx) -> list[RenewalRow]:
        stmt = (select(ReviewItemRow, OutputPackageRow)
                .join(OutputPackageRow,
                      col(ReviewItemRow.output_package_id) == col(OutputPackageRow.id))
                .where(col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                       col(ReviewItemRow.workflow) == WORKFLOW))
        rows: list[RenewalRow] = []
        for item, pkg in (await session.execute(stmt)).all():
            payload = pkg.payload or {}
            row_payload = payload["row"]
            row = RenewalRow(**{"subject": row_payload.get("id", ""), **row_payload})
            row.status = item.status.value if hasattr(item.status, "value") else str(item.status)
            rows.append(row)
        return rows

    async def get_detail(
        self, session: AsyncSession, ctx: Ctx, submission_id: str
    ) -> RenewalDetail | None:
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
        return RenewalDetail.model_validate(detail_payload)

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
            raise KeyError(f"no renewal review item for submission '{submission_id}'")
        result = await self.review_queue.act(session, ctx, item.id, review_action, amount)
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
        """Exports every renewal currently in this tenant's list — regardless of
        review status — as one row each into the shared spreadsheet's "Renewal
        Management" tab. Manual, button-triggered; never fails the caller."""
        sheet_id = await resolve_sheet_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        sheet_rows = [
            [r.id, r.subject, r.recommendation, r.retention, r.priorPremium, r.indicated, r.status]
            for r in rows
        ]
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_append_rows(
            connector, ctx, sheet_id, sheet_rows, tab=_SHEET_TAB, header=_SHEET_HEADER
        )

    async def export_all_to_drive(self, session: AsyncSession, ctx: Ctx) -> str:
        """Generates one PDF (one page per renewal currently in this tenant's
        list, regardless of review status) and uploads it to the tenant's
        connected Drive. Manual, button-triggered."""
        folder_id = await resolve_drive_folder_id(session, ctx.tenant_id, get_settings())
        rows = await self.list_rows(session, ctx)
        pdf_rows = [
            [
                ("Renewal ID", r.id), ("Subject", r.subject),
                ("Recommendation", r.recommendation), ("Retention", r.retention),
                ("Prior Premium", r.priorPremium), ("Indicated", r.indicated),
                ("Status", r.status),
            ]
            for r in rows
        ]
        pdf_bytes = render_bulk_summary_pdf("Renewal Management", pdf_rows)
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        return await try_put_file(
            connector, ctx, folder_id, f"renewal-management-{timestamp}.pdf",
            pdf_bytes, "application/pdf",
        )

    async def add_to_calendar(self, session: AsyncSession, ctx: Ctx, submission_id: str) -> str:
        """Creates (or updates) one all-day Google Calendar event for ONE renewal
        — a per-item action, dated at that renewal's own expiration date
        (``today + daysToExpiration``, per FR-1's 60-90-day-before-expiration
        reminder window, computed fresh at export time). Manual, button-triggered;
        never fails the caller: an unconnected Calendar integration is a normal,
        logged skip. The event's id is deterministic (derived from the renewal
        id) so a repeat click updates the same event instead of duplicating it."""
        rows = await self.list_rows(session, ctx)
        row = next((r for r in rows if r.id == submission_id), None)
        if row is None:
            raise KeyError(f"no renewal-management row for submission '{submission_id}'")
        expiration = (datetime.now(UTC).date() + timedelta(days=row.daysToExpiration)).isoformat()
        connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
        return await try_create_event(
            connector, ctx, f"renewal-management-{row.id}",
            summary=f"Renewal due: {row.insured} ({row.recommendation})",
            description=(
                f"Renewal {row.id} — {row.insured}. Recommendation: {row.recommendation}. "
                f"Status: {row.status}."
                + (" Lapse risk flagged." if row.lapseRisk else "")
            ),
            start_date=expiration, end_date=expiration,
        )
