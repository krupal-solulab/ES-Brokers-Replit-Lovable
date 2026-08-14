"""Pydantic output schemas for MGA Claims Intake Coordination (Workflow-10). Shapes
follow the real PRD's Section 7 Data Schema directly (camelCase for the FE, same
convention as every other workflow's schema.py) — built against the real Workflow-10
dataset, not a speculative pre-dataset design.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PhiGateOut(BaseModel):
    triggered: bool
    baaConfirmed: bool
    medicalContentProcessingStatus: str  # BLOCKED | PERMITTED | NOT_TRIGGERED


class SettlementAuthorityCheckOut(BaseModel):
    estimatedReserve: float | None
    ceiling: float | None
    withinCeiling: bool | None  # None when authority was never delegated — not evaluated


class ProceduralSignalOut(BaseModel):
    description: str
    loggedOnly: bool = True


class WriteBackRecordOut(BaseModel):
    logged: bool
    bordereauSchemaValidated: bool
    claimNumber: str | None = None


class ActivityEntry(BaseModel):
    at: str
    who: str
    what: str
    ctx: str | None = None
    conf: str | None = None


class ClaimsIntakeDetail(BaseModel):
    claimId: str
    policyNumber: str | None
    namedInsured: str
    carrier: str | None
    lossDescription: str
    authorityClassification: str  # NO_AUTHORITY_DELEGATED | WITHIN_AUTHORITY | EXCEEDS_AUTHORITY
    bodilyInjuryInvolved: bool
    phiGate: PhiGateOut
    settlementAuthorityCheck: SettlementAuthorityCheckOut
    proceduralSignals: list[ProceduralSignalOut] = Field(default_factory=list)
    writeBackRecord: WriteBackRecordOut
    routingOutcome: str  # HANDLED_INTERNALLY | REFERRED_EXCEEDS_AUTHORITY | FORWARDED_NO_AUTHORITY
    rationale: str
    status: str  # READY_FOR_INTERNAL_HANDLING | MUST_REFER | FORWARD_ONLY | PHI_BLOCKED
    activity: list[ActivityEntry] = Field(default_factory=list)
    # The real, persisted human-review state (pending/approved/escalated/sent/issued) —
    # lets the frontend render "already decided" after a page reload, instead of relying
    # on its own in-memory action state. Distinct from `status` above, which is this
    # workflow's own triage/routing outcome, not a review-queue state.
    reviewStatus: str | None = None


class ClaimsIntakeRow(BaseModel):
    """Inbox/list row for the Claims Intake screen."""

    id: str
    policy: str | None
    insured: str
    carrier: str | None
    authorityClassification: str
    routingOutcome: str
    status: str


class ActRequest(BaseModel):
    action: str  # approve | send | escalate
    note: str | None = None
