"""Pydantic output schemas for MGA Bordereau Reporting.

Shapes follow the PRD's Section 7.2 Bordereau Compilation Output Schema directly
(camelCase for the FE, same convention as every other workflow's schema.py).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompletenessCheckOut(BaseModel):
    status: str  # COMPLETE | GAP_DETECTED
    missingTransactions: list[str] = Field(default_factory=list)


class FormatComplianceCheckOut(BaseModel):
    status: str  # COMPLIANT | NON_COMPLIANT
    issues: list[str] = Field(default_factory=list)


class ReconciliationCheckOut(BaseModel):
    status: str  # MATCHED | DISCREPANCY | NOT_APPLICABLE
    discrepancyDetail: list[str] = Field(default_factory=list)


class DataCurrencyCheckOut(BaseModel):
    status: str  # CURRENT | STALE_DATA_DETECTED
    staleItems: list[str] = Field(default_factory=list)


class TimelinessCheckOut(BaseModel):
    daysRemaining: int
    compilationTimeNeededDays: int
    urgent: bool
    detail: str


class ActivityEntry(BaseModel):
    at: str
    who: str
    what: str
    ctx: str | None = None
    conf: str | None = None


class BordereauDetail(BaseModel):
    bordereauId: str
    bordereauType: str  # PREMIUM | CLAIMS
    carrierName: str
    reportingPeriod: str
    dueDate: str
    completenessCheck: CompletenessCheckOut
    formatComplianceCheck: FormatComplianceCheckOut
    reconciliationCheck: ReconciliationCheckOut
    dataCurrencyCheck: DataCurrencyCheckOut
    timelinessCheck: TimelinessCheckOut | None = None
    status: str  # READY_TO_SUBMIT | BLOCKED | DISCREPANCY_FLAGGED | URGENT_ALERT
    rationale: str
    activity: list[ActivityEntry] = Field(default_factory=list)
    # The real, persisted human-review state (pending/approved/escalated/sent/issued) —
    # lets the frontend render "already decided" after a page reload, instead of relying
    # on its own in-memory action state.
    reviewStatus: str | None = None


class BordereauRow(BaseModel):
    """Inbox/list row for the Bordereau Reporting screen."""

    id: str
    carrierName: str
    reportingPeriod: str
    status: str


class ActRequest(BaseModel):
    action: str  # approve | send | escalate
