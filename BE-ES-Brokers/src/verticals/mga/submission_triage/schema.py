"""Pydantic output schemas for MGA Submission Triage.

Field names are camelCase to map 1:1 onto the MGA-FE ``TriageDetail`` / ``Submission``
shapes (mocks.ts). These are workflow-local response models — the frozen ``core/common``
contracts are unchanged.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TriageDoc(BaseModel):
    name: str
    kind: str
    pages: int
    fields: int
    confidence: float
    classified: bool


class TriageBroker(BaseModel):
    """The submitting broker's real identity, parsed fresh from the inbound email's
    Gmail "From" header (never fabricated) — same shape as Renewal Management's
    ``RenewalBroker``, since Broker Copilot reads either one generically off
    ``detail.broker``."""

    name: str
    agency: str
    tenure: str
    note: str
    email: str = ""


class ExtractedFieldOut(BaseModel):
    key: str
    label: str
    value: str | None
    required: bool
    confidence: float
    source: str | None = None


class ConsistencyCheck(BaseModel):
    label: str
    detail: str
    status: str  # ok | warn | fail


class MissingItem(BaseModel):
    item: str
    reason: str
    severity: str  # required | recommended


class RiskFactor(BaseModel):
    name: str
    value: str
    weight: int


class AppetiteResultOut(BaseModel):
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


class LossMetrics(BaseModel):
    totalIncurred: str
    totalPaid: str
    openClaims: int
    years: int
    required: int
    trend: str  # improving | worsening | flat


class TriageMeta(BaseModel):
    received: list[str]
    lowConfidence: list[str]
    timestamp: str


class TriageDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    subject: str
    recommendation: str
    confidence: float
    hardRulePassed: bool
    failedRules: list[str]
    processing: str
    rulesVersion: str
    meta: TriageMeta
    docs: list[TriageDoc]
    fields: list[ExtractedFieldOut]
    loss: LossMetrics
    consistency: list[ConsistencyCheck]
    missingInfo: list[MissingItem]
    factors: list[RiskFactor]
    narrative: str
    citations: list[str]
    appetite: list[AppetiteResultOut]
    activity: list[ActivityEntry]
    # The submitting broker's real identity, parsed from the inbound email's Gmail
    # "From" header (never fabricated) — None only if no email was found (e.g. a
    # fixture with no From header), never a placeholder. Broker Copilot reads this to
    # populate a draft's real recipient address.
    broker: TriageBroker | None = None
    # The real, persisted human-review state (ReviewStatus: pending/approved/escalated/
    # sent/issued) — lets the frontend render "already decided" after a page reload or
    # navigation, instead of relying on its own in-memory action state, which is lost on
    # remount. None only if no ReviewItem exists yet for this submission (shouldn't
    # happen in practice, since triage always enqueues one).
    reviewStatus: str | None = None


class SubmissionRow(BaseModel):
    """Inbox/list row — the MGA-FE ``Submission`` shape."""

    id: str
    subject: str
    insured: str
    industry: str
    state: str
    tiv: str
    premium: str
    score: int | None
    appetite: str
    recommendation: str
    status: str
    received: str


class InboxRow(BaseModel):
    """Live, unfiltered mailbox row — a Gmail message that may or may not have been
    triaged yet. Distinct from ``SubmissionRow``, which only covers submissions that
    have already been through the triage pipeline."""

    id: str
    subject: str
    triaged: bool


class ActRequest(BaseModel):
    action: str  # approve | send | escalate
    amount: float | None = None
    note: str | None = None
