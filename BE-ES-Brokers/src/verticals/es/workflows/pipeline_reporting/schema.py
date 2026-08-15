"""Pydantic output schema for Pipeline & Carrier Performance Reporting —
mirrors PRD §7's schema closely. Deviations, all deliberate:

- ``remarketing_value[].outcome_type`` adds a third value,
  ``not_remarketed``, beyond the literal schema's
  ``savings_identified | confirmation_value`` — an account that was never
  actually shopped is genuinely neither, same "add a real third state"
  discipline used throughout this vertical (``PENDING_DETERMINATION``,
  ``unstated`` reason_scope, etc.).
- ``funnel[].count``/``pct_of_prior_stage`` are nullable — a data-gap
  stage (PR-06) has neither, by design.
- ``overall_conversion_pct`` and ``carrier_performance[].overall_hit_rate``
  are additive (not in the literal §7 schema) — both appear in this
  dataset's own expected report output, so they're included for FE
  parity; the funnel's overall figure is withheld whenever any gap
  exists (see ``reporting_engine.build_funnel``).
- No revenue-attribution field anywhere (PR-04) — explicitly out of
  scope per the PRD ("do not build this rule from assumption").

Not a ``core.common`` contract; free to evolve.
"""

from __future__ import annotations

from pydantic import BaseModel


class DataGapOut(BaseModel):
    stage: str
    reason: str


class DataCompletenessOut(BaseModel):
    status: str  # COMPLETE | PARTIAL
    gaps: list[DataGapOut] = []


class FunnelStageOut(BaseModel):
    stage: str
    count: int | None = None
    pct_of_prior_stage: float | None = None


class CarrierPerformanceOut(BaseModel):
    carrier_name: str
    submissions_approached: int
    quote_rate: float
    bind_rate: float
    overall_hit_rate: float
    low_volume_flag: bool = False


class RemarketOutcomeOut(BaseModel):
    account: str
    trigger_level: str
    outcome_type: str  # savings_identified | confirmation_value | not_remarketed
    savings_amount: float | None = None
    note: str | None = None


class TimeToPlacementOut(BaseModel):
    """PR-03. ``avg_days`` is RAW elapsed time (submission matched -> bound).
    ``delay_excluded=True`` when FR-4 carrier-attributed figures are also
    available (see ``time_to_placement_carrier_attributed``); False when no
    PipelineStageEvent rows exist for any submission in this report period."""

    carrier_name: str
    submissions_bound: int
    avg_days: float
    low_volume_flag: bool = False
    delay_excluded: bool = False


class TimeToPlacementCarrierAttributedOut(BaseModel):
    """FR-4. ``avg_days_raw`` == TimeToPlacementOut.avg_days (kept for direct
    comparison — no regression).  ``avg_days_carrier_attributed`` is raw minus
    the total duration of completed BROKER/AGENT PipelineStageEvent spans.
    A submission with no recorded BLOCKED span contributes raw == attributed.
    Only completed spans (exited_at set) are subtracted — open spans are
    excluded, never estimated (KB06)."""

    carrier_name: str
    submissions_bound: int
    avg_days_raw: float
    avg_days_carrier_attributed: float
    low_volume_flag: bool = False
    delay_excluded: bool = True


class RevenueAttributionOut(BaseModel):
    """FR-6 / PR-04. Always ``provisional=True`` — must be confirmed with the
    design partner before presenting as a confirmed figure.  ``not_configured``
    is True when no commission rate exists for this carrier: the figure is
    absent, never guessed (KB06 / Deterministic Logic Boundary)."""

    carrier_name: str
    submissions_bound: int
    bound_premium_total: float | None = None
    commission_rate: float | None = None
    estimated_commission: float | None = None
    not_configured: bool = False
    provisional: bool = True


class PipelineReportPayload(BaseModel):
    report_id: str
    period: str
    data_completeness: DataCompletenessOut = DataCompletenessOut(status="COMPLETE", gaps=[])
    funnel: list[FunnelStageOut] = []
    overall_conversion_pct: float | None = None
    carrier_performance: list[CarrierPerformanceOut] = []
    time_to_placement: list[TimeToPlacementOut] = []
    # FR-4: carrier-attributed time (BROKER/AGENT spans subtracted). Empty
    # when no PipelineStageEvent rows exist for this tenant — the raw metric
    # above is always present as the safe fallback.
    time_to_placement_carrier_attributed: list[TimeToPlacementCarrierAttributedOut] = []
    # FR-6 / PR-04: always provisional; "not_configured" when commission rates
    # are absent for a carrier rather than emitting a guessed figure.
    revenue_attribution: list[RevenueAttributionOut] = []
    remarketing_value: list[RemarketOutcomeOut] = []
