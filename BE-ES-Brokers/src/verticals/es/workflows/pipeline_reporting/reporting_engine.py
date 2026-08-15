"""Native PR-01..PR-06 logic. None of this fits the generic 6-check rules
engine — aggregation/formatting/annotation reasoning (Option-A precedent,
same as every prior E&S workflow's own engine module).

PR-06 is this PRD's equivalent of every other workflow's highest-stakes
gate: this PRD's own risk register calls a single smoothed-over data gap
"the direct throughline back to the very first critique in this entire
project" (the original landing page's fabricated dashboard stats). Every
function here is written so that a missing figure renders as an explicit
gap, never an interpolated or silently-omitted one.

FR-4 (carrier-attributed time-to-placement): now computable from
PipelineStageEvent rows written by Package Assembly's run_live() at BLOCKED
entry/exit. Delay exclusion subtracts ONLY spans explicitly attributed to
BROKER/AGENT — never inferred. A submission with no BLOCKED span has
carrier_attributed_days == raw_days (zero broker delay). Raw elapsed is
kept alongside (no regression).

FR-6 / PR-04 (revenue attribution): computed from a configurable
commission-structure config (env/settings-driven, per-tenant overridable via
Admin Panel). Every figure carries provisional=True until confirmed with the
design partner. If commission config is absent for a carrier: "not_configured"
is set and no figure is emitted — never a guessed number (KB06).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

MIN_RELIABLE_VOLUME = 10  # placeholder — validate with a real design partner (PR-02)

_FUNNEL_STAGES = [
    ("submissions_received", "Submissions Received"),
    ("matched_to_carrier", "Matched to Carrier"),
    ("packages_assembled", "Packages Assembled"),
    ("quotes_received", "Quotes Received"),
    ("compared_and_selected", "Compared & Selected"),
    ("bound", "Bound"),
]


@dataclass(frozen=True)
class FunnelStage:
    stage: str
    count: int | None
    pct_of_prior_stage: float | None


@dataclass(frozen=True)
class DataGap:
    stage: str
    reason: str


@dataclass(frozen=True)
class FunnelResult:
    stages: list[FunnelStage]
    gaps: list[DataGap]
    overall_conversion_pct: float | None  # None whenever ANY gap exists — see build_funnel


def build_funnel(data: dict[str, Any]) -> FunnelResult:
    """PR-01/PR-06. A funnel-stage value that isn't an int is a logging
    gap (Scenario 03's ``compared_and_selected`` is the string
    "UNKNOWN - Quote Comparison workflow logging gap identified for 2
    weeks in August (system migration)") — its text becomes the gap's
    reason, its own percentage is never computed, and the NEXT stage's
    percentage is also never computed (its denominator is unknown) even
    though that next stage's raw count may still be reliable on its own
    (Scenario 03's Bound: 47 — bind logging itself is unaffected).

    ``overall_conversion_pct`` (submissions-received -> bound) is
    deliberately withheld whenever ANY gap exists anywhere in the funnel,
    even though its own two endpoints might both be numeric — showing a
    clean top-line conversion figure right next to an explicitly-flagged
    gap would undercut the gap's prominence, which is exactly the
    smoothing-over this rule exists to prevent.
    """
    stages: list[FunnelStage] = []
    gaps: list[DataGap] = []
    prior_count: int | None = None

    for key, label in _FUNNEL_STAGES:
        raw = data.get(key)
        if isinstance(raw, bool) or not isinstance(raw, int):
            gaps.append(DataGap(stage=label, reason=str(raw)))
            stages.append(FunnelStage(stage=label, count=None, pct_of_prior_stage=None))
            prior_count = None
            continue

        pct = (
            round(raw / prior_count * 100, 1)
            if prior_count is not None and prior_count > 0
            else None
        )
        stages.append(FunnelStage(stage=label, count=raw, pct_of_prior_stage=pct))
        prior_count = raw

    first = stages[0].count if stages else None
    last = stages[-1].count if stages else None
    overall = (
        round(last / first * 100, 1)
        if not gaps and first and last is not None and first > 0
        else None
    )
    return FunnelResult(stages=stages, gaps=gaps, overall_conversion_pct=overall)


@dataclass(frozen=True)
class CarrierPerformance:
    carrier_name: str
    submissions_approached: int
    quote_rate: float
    bind_rate: float
    overall_hit_rate: float
    low_volume_flag: bool


def build_carrier_performance(
    carrier_activity: list[dict[str, Any]], *, min_reliable_volume: int = MIN_RELIABLE_VOLUME
) -> list[CarrierPerformance]:
    """PR-02. Ordered by ``submissions_approached`` DESCENDING — never by
    hit-rate. Sorting by rate alone would visually rank a low-volume
    carrier's inflated percentage (Vantage's 100% of 4) above a
    higher-volume, more reliable one (Ironclad's 63.6% of 22), which is
    exactly the false-precision problem this rule exists to catch."""
    results = []
    for c in carrier_activity:
        approached = int(c["submissions_approached"])
        quoted = int(c["quotes_issued"])
        binds = int(c["binds"])
        quote_rate = round(quoted / approached * 100, 1) if approached > 0 else 0.0
        bind_rate = round(binds / quoted * 100, 1) if quoted > 0 else 0.0
        overall_hit_rate = round(binds / approached * 100, 1) if approached > 0 else 0.0
        results.append(
            CarrierPerformance(
                carrier_name=c["carrier_name"],
                submissions_approached=approached,
                quote_rate=quote_rate,
                bind_rate=bind_rate,
                overall_hit_rate=overall_hit_rate,
                low_volume_flag=approached < min_reliable_volume,
            )
        )
    return sorted(results, key=lambda r: r.submissions_approached, reverse=True)


@dataclass(frozen=True)
class TimeToPlacement:
    carrier_name: str
    submissions_bound: int
    avg_days: float
    low_volume_flag: bool


def build_time_to_placement(
    placements: list[dict[str, Any]], *, min_reliable_volume: int = MIN_RELIABLE_VOLUME
) -> list[TimeToPlacement]:
    """PR-03: raw elapsed time (submission matched -> bound), per carrier.
    FR-4's broker/agent-delay exclusion is deliberately NOT computed here —
    see ``TimeToPlacementOut``'s docstring in schema.py for why no real
    data exists anywhere to measure it from. ``placements`` is
    ``[{"carrier_name": str, "days": int}, ...]``, one entry per real bound
    submission, already elapsed-time-computed by the caller (this function
    only aggregates per carrier, never touches raw timestamps itself)."""
    by_carrier: dict[str, list[int]] = {}
    for p in placements:
        by_carrier.setdefault(p["carrier_name"], []).append(p["days"])

    results = [
        TimeToPlacement(
            carrier_name=name,
            submissions_bound=len(days_list),
            avg_days=round(sum(days_list) / len(days_list), 1),
            low_volume_flag=len(days_list) < min_reliable_volume,
        )
        for name, days_list in by_carrier.items()
    ]
    return sorted(results, key=lambda r: r.submissions_bound, reverse=True)


@dataclass(frozen=True)
class RemarketOutcome:
    account: str
    trigger_level: str
    outcome_type: str  # savings_identified | confirmation_value | not_remarketed
    savings_amount: float | None
    note: str | None


@dataclass(frozen=True)
class TimeToPlacementCarrierAttributed:
    """FR-4: time-to-placement with BROKER/AGENT delay subtracted.

    ``avg_days_raw`` == existing ``TimeToPlacement.avg_days`` — kept for
    direct comparison; no regression.  ``avg_days_carrier_attributed`` is the
    same figure minus the total duration of BLOCKED spans attributed to
    BROKER/AGENT for each submission.  When no stage events exist for a
    submission, the carrier-attributed figure equals the raw figure
    (zero broker delay recorded).
    """

    carrier_name: str
    submissions_bound: int
    avg_days_raw: float
    avg_days_carrier_attributed: float
    low_volume_flag: bool


def _broker_attributed_days(
    submission_id: str,
    stage_events: list[dict[str, Any]],
) -> float:
    """Sum of completed BROKER/AGENT stage spans for one submission.

    Only completed spans (exited_at set) are counted — an open span means the
    submission is still BLOCKED right now; subtracting an unknown duration
    would fabricate a figure (KB06).  Open spans are intentionally excluded.
    """
    total = 0.0
    for ev in stage_events:
        if ev.get("submission_ref") != submission_id:
            continue
        if ev.get("attribution") not in ("BROKER", "AGENT"):
            continue
        entered_raw = ev.get("entered_at")
        exited_raw = ev.get("exited_at")
        if not entered_raw or not exited_raw:
            continue  # open or invalid span — never subtract unknown duration
        entered = entered_raw if isinstance(entered_raw, datetime) else datetime.fromisoformat(str(entered_raw))
        exited = exited_raw if isinstance(exited_raw, datetime) else datetime.fromisoformat(str(exited_raw))
        span_days = (exited.date() - entered.date()).days
        if span_days > 0:
            total += span_days
    return total


def build_time_to_placement_carrier_attributed(
    placements: list[dict[str, Any]],
    stage_events: list[dict[str, Any]],
    *,
    min_reliable_volume: int = MIN_RELIABLE_VOLUME,
) -> list[TimeToPlacementCarrierAttributed]:
    """FR-4: per-carrier time-to-placement minus BROKER/AGENT-attributed spans.

    ``placements`` must include ``submission_id`` (added by live_aggregator)
    alongside ``carrier_name`` and ``days``.  ``stage_events`` is a list of
    dicts with keys ``submission_ref``, ``entered_at``, ``exited_at``,
    ``attribution``.

    A submission with no matching stage events gets
    ``carrier_attributed_days == raw_days`` — the two figures are identical
    when no BLOCKED span was recorded (zero broker delay, not missing data).
    """
    by_carrier: dict[str, list[tuple[int, float]]] = {}  # name -> [(raw_days, attributed_days)]
    for p in placements:
        name = p["carrier_name"]
        raw = p["days"]
        sub_id = p.get("submission_id", "")
        broker_days = _broker_attributed_days(sub_id, stage_events) if sub_id else 0.0
        attributed = max(0.0, raw - broker_days)
        by_carrier.setdefault(name, []).append((raw, attributed))

    results = [
        TimeToPlacementCarrierAttributed(
            carrier_name=name,
            submissions_bound=len(pairs),
            avg_days_raw=round(sum(r for r, _ in pairs) / len(pairs), 1),
            avg_days_carrier_attributed=round(sum(a for _, a in pairs) / len(pairs), 1),
            low_volume_flag=len(pairs) < min_reliable_volume,
        )
        for name, pairs in by_carrier.items()
    ]
    return sorted(results, key=lambda r: r.submissions_bound, reverse=True)


@dataclass(frozen=True)
class RevenueAttribution:
    """FR-6 / PR-04: estimated commission per carrier, always provisional.

    ``not_configured`` is True when no commission rate exists for this
    carrier — the figure is explicitly absent, never guessed (KB06).
    ``provisional`` is always True — the design partner must confirm the
    commission structure before any figure is presented as confirmed.
    """

    carrier_name: str
    submissions_bound: int
    bound_premium_total: float | None  # sum of bound premiums from BI payloads
    commission_rate: float | None      # configured rate (fraction, e.g. 0.12)
    estimated_commission: float | None # bound_premium_total * commission_rate; None if not_configured
    not_configured: bool
    provisional: bool = True


def parse_commission_config(config_json: str) -> dict[str, float]:
    """Parse commission config JSON string.  Returns empty dict on any parse failure
    — the caller then renders "not configured" for all carriers (KB06)."""
    if not config_json or config_json.strip() in ("", "{}"):
        return {}
    try:
        parsed = json.loads(config_json)
        return {k: float(v) for k, v in parsed.items() if isinstance(v, (int, float))}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def build_revenue_attribution(
    bound_submissions: list[dict[str, Any]],
    commission_config: dict[str, float],
    *,
    min_reliable_volume: int = MIN_RELIABLE_VOLUME,
) -> list[RevenueAttribution]:
    """FR-6 / PR-04: estimated revenue per carrier, always provisional.

    ``bound_submissions`` is ``[{"carrier_name": str, "bound_premium": float}, ...]``
    — one entry per bound submission with a real premium value.  Submissions
    without a premium are excluded (never fabricated).

    ``commission_config`` maps carrier_name -> rate (fraction).  When no rate
    exists for a carrier, ``not_configured=True`` and ``estimated_commission``
    is None — the report still generates, that carrier's row shows
    "not configured" instead of a dollar figure.
    """
    by_carrier: dict[str, list[float]] = {}
    for s in bound_submissions:
        name = s.get("carrier_name")
        premium = s.get("bound_premium")
        if name and premium is not None:
            by_carrier.setdefault(name, []).append(float(premium))

    results = []
    for name, premiums in by_carrier.items():
        total = sum(premiums)
        rate = commission_config.get(name)
        results.append(RevenueAttribution(
            carrier_name=name,
            submissions_bound=len(premiums),
            bound_premium_total=round(total, 2),
            commission_rate=rate,
            estimated_commission=round(total * rate, 2) if rate is not None else None,
            not_configured=(rate is None),
            provisional=True,
        ))
    return sorted(results, key=lambda r: r.submissions_bound, reverse=True)


def categorize_remarket_outcome(outcome: dict[str, Any]) -> RemarketOutcome:
    """PR-05. Three genuinely distinct outcomes, never collapsed to a
    single savings figure:
    - ``not_remarketed``: the account was never actually shopped (e.g.
      suppressed by its own remarketing history per RR-08) — excluded
      from savings math entirely, not a $0 result.
    - ``confirmation_value``: the account WAS remarketed and the
      incumbent was confirmed the best option — $0 in direct savings but
      a real, valuable outcome (per Renewal Remarketing's own RR-04
      interpretation guide), never reported as a failure.
    - ``savings_identified``: a genuine quantified savings figure.
    """
    trigger = str(outcome.get("trigger", ""))
    savings = outcome.get("savings_identified")
    trigger_level = trigger.split(" - ")[0].strip()

    savings_note_excludes = isinstance(savings, str) and "not remarketed" in savings.lower()
    if trigger_level == "no_remarket" or savings_note_excludes:
        return RemarketOutcome(
            account=outcome["account"], trigger_level=trigger_level,
            outcome_type="not_remarketed", savings_amount=None, note=outcome.get("note"),
        )

    if isinstance(savings, int | float) and savings > 0:
        return RemarketOutcome(
            account=outcome["account"], trigger_level=trigger_level,
            outcome_type="savings_identified", savings_amount=float(savings),
            note=outcome.get("note"),
        )

    return RemarketOutcome(
        account=outcome["account"], trigger_level=trigger_level,
        outcome_type="confirmation_value", savings_amount=None, note=outcome.get("note"),
    )
