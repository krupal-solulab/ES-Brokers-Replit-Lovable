"""Builds real Appetite Governance requests from what's actually persisted, instead of a
fixture, for the sub-features that don't require fabricating data:

- AG-05 (carrier delegated-authority audit): real decision counts per workflow plus real
  ceiling-breach counts from Bind & Issuance.
- AG-02 (decision trail): real per-decision records — workflow, outcome, rules version,
  and the underwriter who took the last human action on it (or "system (AI)" if none
  has yet) — built from ``Decision``/``OutputPackage``/``AuditEntry`` rows.
- AG-04 (override pattern detection): a real "override" is inferred as a human
  ``approve`` action on a submission whose AI decision was DECLINE or REQUEST_INFO —
  there is no ``ReviewAction.OVERRIDE`` in active use anywhere in this codebase, only
  approve/escalate/send, so this is the honest, inferable proxy. The override *reason*
  comes from ``AuditEntry.detail["note"]`` when the underwriter provided one.

AG-03 (rule version drift) and AG-06 (portfolio concentration) stay fixture-only: AG-03
needs a rules version that actually changes over time (today's version is a constant,
never varied, so there is nothing real to detect drift against); AG-06 needs a stable
class/carrier/loss-history figure that doesn't survive being persisted anywhere (see the
Workflow-06/07 research this session) — building either live today would mean inventing
data, not reading it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.common.dtos import Ctx
from core.common.enums import DecisionOutcome
from core.models import AuditEntry as AuditEntryRow
from core.models import Decision as DecisionRow
from core.models import OutputPackage as OutputPackageRow
from verticals.mga.models import MgaBindResult
from verticals.mga.renewal_management.service import RULES_VERSION as _RENEWAL_RULES_VERSION
from verticals.mga.submission_triage.service import RULES_VERSION as _TRIAGE_RULES_VERSION

_SOURCE_WORKFLOWS = (
    "submission-triage", "renewal-management", "bind-issuance", "endorsement-processing",
)
_EXCEEDS_CEILING_REFERRAL_REQUIRED = "EXCEEDS_CEILING_REFERRAL_REQUIRED"

# The rules version every Triage/Renewal decision currently cites — each workflow's own
# real constant (never yet varied at runtime, so this is the honest "version applied"
# value today, not a placeholder). Endorsement/Bind have no equivalent versioned
# ruleset — their decisions cite "n/a" rather than a fabricated version string.
_RULES_VERSION_BY_WORKFLOW = {
    "submission-triage": _TRIAGE_RULES_VERSION,
    "renewal-management": _RENEWAL_RULES_VERSION,
}


async def build_audit_report_request(
    session: AsyncSession, ctx: Ctx, *, carrier_name: str, period: str, requested_by: str,
) -> dict[str, Any]:
    stmt = (
        select(OutputPackageRow.workflow, func.count())
        .where(col(OutputPackageRow.tenant_id) == ctx.tenant_id,
               col(OutputPackageRow.workflow).in_(_SOURCE_WORKFLOWS))
        .group_by(OutputPackageRow.workflow)
    )
    counts_by_workflow = dict((await session.execute(stmt)).all())

    breach_stmt = select(func.count()).where(
        col(MgaBindResult.tenant_id) == ctx.tenant_id,
        col(MgaBindResult.authority_outcome) == _EXCEEDS_CEILING_REFERRAL_REQUIRED,
    )
    breaches_referred = (await session.execute(breach_stmt)).scalar_one()

    return {
        "report_type": "CARRIER_DELEGATED_AUTHORITY_AUDIT",
        "carrier_name": carrier_name,
        "period": period,
        "requested_by": requested_by,
        "logged_decisions_available": {
            "triage_decisions": counts_by_workflow.get("submission-triage", 0),
            "renewal_decisions": counts_by_workflow.get("renewal-management", 0),
            "bind_decisions": counts_by_workflow.get("bind-issuance", 0),
            "endorsement_decisions": counts_by_workflow.get("endorsement-processing", 0),
            "authority_ceiling_breaches_referred": breaches_referred,
            # Not tracked anywhere yet — no workflow records a carrier's response to a
            # referral. Reported as 0 (honest "none recorded"), never fabricated.
            "authority_ceiling_breaches_referred_and_approved_by_carrier": 0,
            "authority_ceiling_breaches_referred_and_declined_by_carrier": 0,
        },
    }


_DECISION_WORKFLOWS = ("submission-triage", "renewal-management")
_WORKFLOW_LABEL = {"submission-triage": "Submission Triage", "renewal-management": "Renewal Management"}


async def build_decision_trail_request(
    session: AsyncSession, ctx: Ctx, *, period: str,
) -> dict[str, Any]:
    """AG-02: a real decision-trail record per Triage/Renewal decision — only these two
    emit a rules-version-scoped outcome (`Decision` row) at all; Endorsement/Bind's
    decisions are engine-computed and don't carry a comparable rules-version concept, so
    including them here would mean padding the trail with an "n/a" that adds no signal."""
    decisions_stmt = (
        select(DecisionRow, OutputPackageRow.workflow)
        .join(OutputPackageRow, col(DecisionRow.submission_id) == col(OutputPackageRow.submission_id))
        .where(col(DecisionRow.tenant_id) == ctx.tenant_id,
               col(OutputPackageRow.workflow).in_(_DECISION_WORKFLOWS))
    )
    rows = (await session.execute(decisions_stmt)).all()

    submission_ids = [d.submission_id for d, _ in rows]
    underwriter_by_submission: dict[str, str] = {}
    if submission_ids:
        # Latest human AuditEntry per submission — whoever most recently acted on it.
        # A submission no human has touched yet has no entry here, so it's honestly
        # attributed to the system rather than a guessed name.
        audit_stmt = (
            select(AuditEntryRow)
            .where(col(AuditEntryRow.tenant_id) == ctx.tenant_id,
                   col(AuditEntryRow.actor) == "human")
            .order_by(col(AuditEntryRow.at).asc())
        )
        for entry in (await session.execute(audit_stmt)).scalars().all():
            sub_id = (entry.detail or {}).get("submission")
            if sub_id in submission_ids:
                underwriter_by_submission[sub_id] = entry.who

    decisions_logged = [
        {
            "workflow": _WORKFLOW_LABEL[workflow],
            "submission_id": decision.submission_id,
            "decision": decision.outcome.value if hasattr(decision.outcome, "value") else str(decision.outcome),
            "rules_version_applied": _RULES_VERSION_BY_WORKFLOW.get(workflow, "n/a"),
            "underwriter": underwriter_by_submission.get(decision.submission_id, "system (AI) — no human action yet"),
        }
        for decision, workflow in rows
    ]

    return {
        "period": period,
        "decisions_logged": decisions_logged,
        "rules_version_active_throughout_period": (
            ", ".join(sorted(set(_RULES_VERSION_BY_WORKFLOW.values()))) or "n/a"),
    }


async def build_override_patterns_request(
    session: AsyncSession, ctx: Ctx,
) -> dict[str, Any]:
    """AG-04: a real "override" inferred as a human `approve` action on a submission
    whose AI decision was DECLINE or REQUEST_INFO — the only override-like event this
    codebase's real action model (approve/escalate/send) can actually produce, since
    `ReviewAction.OVERRIDE` is never invoked by any of the four source workflows today.
    The reason comes from `AuditEntry.detail["note"]` when the underwriter gave one."""
    decisions_stmt = select(DecisionRow).where(col(DecisionRow.tenant_id) == ctx.tenant_id)
    outcome_by_submission = {
        d.submission_id: d.outcome for d in (await session.execute(decisions_stmt)).scalars().all()
    }

    audit_stmt = (
        select(AuditEntryRow)
        .where(col(AuditEntryRow.tenant_id) == ctx.tenant_id,
               col(AuditEntryRow.actor) == "human")
        .order_by(col(AuditEntryRow.at).asc())
    )
    override_events = []
    for entry in (await session.execute(audit_stmt)).scalars().all():
        if not entry.what.startswith("approve"):
            continue
        sub_id = (entry.detail or {}).get("submission")
        outcome = outcome_by_submission.get(sub_id)
        if outcome not in (DecisionOutcome.DECLINE, DecisionOutcome.REQUEST_INFO):
            continue  # approving a PROCEED isn't an override of anything
        override_events.append({
            "underwriter": entry.who,
            "submission_id": sub_id,
            "system_recommendation": outcome.value if hasattr(outcome, "value") else str(outcome),
            "underwriter_decision": "PROCEED",
            "override_reason_logged": (entry.detail or {}).get("note", ""),
        })

    return {"override_events": override_events}
