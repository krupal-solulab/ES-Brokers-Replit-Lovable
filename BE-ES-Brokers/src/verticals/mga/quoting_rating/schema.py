"""Pydantic output schemas for MGA Quoting & Rating Support.

Shapes follow the PRD's Section 7.2 Rating Worksheet Output Schema directly (camelCase
for the FE, same convention as every other workflow's schema.py) — QR-05's full
transparency requirement means every field here is meant to be shown, not summarized.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StateCalculationOut(BaseModel):
    state: str
    ratePlanVersionUsed: str | None
    ratePlanCurrencyCheck: str  # CURRENT | STALE_BLOCKED
    allocatedExposure: float
    basePremium: float | None
    suggestedAdjustmentPct: float | None
    adjustmentGrounding: str | None
    requestedAdjustmentPct: float | None
    appliedAdjustmentPct: float
    adjustmentCapped: bool
    premiumAfterAdjustment: float | None
    minimumPremiumApplied: bool
    finalStatePremium: float | None
    blockedReason: str | None


class BenchmarkComparisonOut(BaseModel):
    priorPremium: float | None
    pctVariance: float | None
    flaggedForReview: bool


class ActivityEntry(BaseModel):
    at: str
    who: str
    what: str
    ctx: str | None = None
    conf: str | None = None


class WorksheetDetail(BaseModel):
    worksheetId: str
    submissionId: str
    namedInsured: str
    classCode: str
    stateCalculations: list[StateCalculationOut] = Field(default_factory=list)
    totalIndicatedPremium: float | None
    benchmarkComparison: BenchmarkComparisonOut
    status: str  # READY_FOR_REVIEW | BLOCKED_STALE_RATE_PLAN — the RATING outcome
    # The underwriter's review-queue status (pending/approved/escalated/...) — distinct
    # from `status` above. Bind & Issuance's real trigger is a worksheet the underwriter
    # has actually approved, not merely one that calculated cleanly (PRD Section 4 step
    # 1: "a finalized...worksheet is accepted"), so the FE needs this to gate "Bind it".
    reviewStatus: str = "pending"
    activity: list[ActivityEntry] = Field(default_factory=list)


class WorksheetRow(BaseModel):
    """Inbox/list row for the Quoting & Rating screen."""

    id: str
    namedInsured: str
    classCode: str
    states: str  # comma-joined for the list view, e.g. "TN, NC, GA, SC"
    totalIndicatedPremium: str
    status: str
    reviewStatus: str = "pending"


class ActRequest(BaseModel):
    action: str  # approve | send | escalate
    accepted_adjustment_pct: float | None = None
