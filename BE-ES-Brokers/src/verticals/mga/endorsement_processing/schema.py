"""Pydantic output schemas for MGA Endorsement / Mid-Term Change Processing.

Shapes are LOCKED to the MGA-FE ``EndorsementDetail`` type (camelCase JSON, mocks.ts):
classification, premiumBearing, premiumDelta, rationale, diff, appetite, hardRulePassed,
schedule. Additive fields beyond the FE's locked type (authorityCheck, carrierReferral,
writeBackRecord) surface the PRD's Section 7.1 schema that the FE type can't express yet
— same convention as Renewal Management's needsInfo/missingInfo/retention extras.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EndDiffRow(BaseModel):
    label: str
    before: str
    after: str
    direction: str  # up | down | same


class EndAppetite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rule: str
    passed: bool = Field(serialization_alias="pass", validation_alias="pass")
    hard: bool
    detail: str


class ActivityEntry(BaseModel):
    at: str
    who: str
    what: str
    ctx: str | None = None
    conf: str | None = None


class AuthorityCheckOut(BaseModel):
    outcome: str  # WITHIN_AUTHORITY | EXCEEDS_CEILING_REFERRAL_REQUIRED | CONFIRMED_EXCLUSION
    delegatedCeiling: str
    resultingTotalPremium: str | None = None
    excludedClassMatched: str | None = None


class CarrierReferralOut(BaseModel):
    drafted: bool
    carrierResponse: str | None = None
    draftText: str | None = None


class WriteBackRecordOut(BaseModel):
    logged: bool
    bordereauSchemaValidated: bool
    transactionType: str | None = None
    policyNumber: str | None = None
    effectiveDate: str | None = None
    premiumDelta: float | None = None


class EndorsementDetail(BaseModel):
    """Locked to the FE ``EndorsementDetail`` shape, plus PRD Section 7.1 additive
    fields (authorityCheck / carrierReferral / writeBackRecord / premiumImpact)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    subject: str = ""
    # FE-locked fields
    classification: str  # ROUTINE | MATERIAL (FE's own type also allows UNDERWRITING_REVIEW)
    premiumBearing: bool
    premiumDelta: str
    rationale: str
    diff: list[EndDiffRow] = Field(default_factory=list)
    appetite: list[EndAppetite] = Field(default_factory=list)
    hardRulePassed: bool
    schedule: list[str] = Field(default_factory=list)
    # workflow extras (additive, PRD Section 7.1)
    endorsementId: str
    policyNumber: str
    namedInsured: str
    requestedChangeType: str
    requestedChangeDetail: str
    status: str  # READY_TO_PROCESS | BLOCKED_REFERRAL | BLOCKED_DECLINED | BLOCKED_STALE_RATE
    authorityCheck: AuthorityCheckOut
    carrierReferral: CarrierReferralOut
    writeBackRecord: WriteBackRecordOut
    activity: list[ActivityEntry] = Field(default_factory=list)
    # The real, persisted human-review state (pending/approved/escalated/sent/issued) —
    # lets the frontend render "already decided" after a page reload, instead of relying
    # on its own in-memory action state. Distinct from `status` above, which is this
    # workflow's own classification/outcome status, not a review-queue state.
    reviewStatus: str | None = None


class EndorsementRow(BaseModel):
    """Inbox/list row — the MGA-FE ``endorsements`` list shape."""

    id: str
    policy: str
    insured: str
    type: str
    requested: str
    impact: str
    status: str


class InboxRow(BaseModel):
    """Live, unfiltered mailbox row — a mid-term-change-request message that may or may
    not have been processed yet. Distinct from ``EndorsementRow``, which only covers
    requests already run through the engine."""

    id: str
    subject: str
    triaged: bool


class ActRequest(BaseModel):
    action: str  # approve | send | escalate
    note: str | None = None
