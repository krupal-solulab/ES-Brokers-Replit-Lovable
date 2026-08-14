"""Pydantic output schemas for MGA Bind Order & Issuance Support.

Shapes follow the PRD's Section 7 data schema directly (camelCase for the FE, same
convention as every other workflow's schema.py).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorksheetReferenceOut(BaseModel):
    worksheetId: str
    worksheetDate: str | None
    premium: float


class StalenessCheckOut(BaseModel):
    daysSinceWorksheet: int | None
    exceedsThreshold: bool
    materialUpdateLoggedSince: bool


class SubjectivityOut(BaseModel):
    description: str
    materiality: str  # routine | material
    status: str  # cleared | open
    lifecycleStage: str = "PRE_BIND"  # PRE_BIND | POST_BIND_ONGOING


class AuthorityReconfirmationOut(BaseModel):
    outcome: str  # WITHIN_AUTHORITY | REQUIRES_RECALCULATION | EXCEEDS_CEILING_REFERRAL_REQUIRED
    checkedPremium: float | None
    delegatedCeiling: float
    referralDraftText: str | None = None


class WriteBackOut(BaseModel):
    logged: bool
    bordereauSchemaValidated: bool


class DiscrepancyOut(BaseModel):
    field: str
    bound: str
    issued: str


class IssuanceReconciliationOut(BaseModel):
    status: str  # NOT_YET_ISSUED | PENDING | CLEAN | DISCREPANCY_FLAGGED | RESOLVED
    discrepancyDetail: list[DiscrepancyOut] = Field(default_factory=list)


class PostBindObligationOut(BaseModel):
    description: str
    dueDate: str | None
    status: str  # open | completed
    reminderDaysBefore: list[int] = Field(default_factory=list)


class DownstreamTriggersOut(BaseModel):
    bindConfirmation: bool
    policyDelivered: bool


class ActivityEntry(BaseModel):
    at: str
    who: str
    what: str
    ctx: str | None = None
    conf: str | None = None


class BindDetail(BaseModel):
    bindId: str
    submissionId: str
    namedInsured: str
    worksheetReference: WorksheetReferenceOut | None
    stalenessCheck: StalenessCheckOut | None
    preBindSubjectivities: list[SubjectivityOut] = Field(default_factory=list)
    authorityReconfirmation: AuthorityReconfirmationOut | None
    bindOrderStatus: str  # BLOCKED | READY | BOUND
    pasWriteBack: WriteBackOut
    issuanceReconciliation: IssuanceReconciliationOut
    postBindObligations: list[PostBindObligationOut] = Field(default_factory=list)
    downstreamTriggersFired: DownstreamTriggersOut
    rationale: str
    activity: list[ActivityEntry] = Field(default_factory=list)
    # The real, persisted human-review state (ReviewStatus: pending/approved/escalated/
    # sent/issued) — lets the frontend render "already decided" after a page reload or
    # navigation, instead of relying on its own in-memory action state, which is lost on
    # remount. None only if no ReviewItem exists yet for this submission (shouldn't
    # happen in practice, since bind evaluation always enqueues one).
    reviewStatus: str | None = None


class BindRow(BaseModel):
    """Inbox/list row for the Bind Order screen."""

    id: str
    namedInsured: str
    premium: str
    status: str
    # The real, persisted human-review state (pending/approved/escalated/sent/issued) —
    # distinct from `status` above (the bind decision outcome: READY/BLOCKED/BOUND).
    # Lets the frontend build a real "escalated to senior" queue without a new endpoint.
    reviewStatus: str


class ActRequest(BaseModel):
    action: str  # approve | send | escalate
    note: str | None = None
