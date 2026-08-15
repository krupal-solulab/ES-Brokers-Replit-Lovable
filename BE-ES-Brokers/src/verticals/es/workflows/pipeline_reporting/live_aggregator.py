"""Additive live-aggregation path for Pipeline & Carrier Performance
Reporting (PR-01/PR-02/PR-05).

Builds a real funnel / carrier-performance / time-to-placement /
remarketing-value / revenue-attribution report from actual ``OutputPackage``
rows across the five source workflows for this tenant, instead of the static
Workflow_19 fixture (``scenario_loader.py``, untouched by this module).

FR-4 carrier-attributed time: PipelineStageEvent rows written by Package
Assembly's run_live() at BLOCKED entry/exit are loaded here and passed to
``build_time_to_placement_carrier_attributed()`` in the reporting engine.
When no stage events exist (e.g. no live packages have been assembled yet),
the carrier-attributed section is empty — the raw metric remains the safe
fallback.

FR-6 / PR-04 revenue attribution: bound premiums extracted from Binder
Issuance payloads (``carrier_confirmation.confirmed_terms.premium``, falling
back to ``requested_bind_terms.premium_estimate``) combined with the
commission config loaded via ``get_effective_setting()`` (per-tenant override)
or the global ``Settings.commission_rates_json`` default. Always provisional.

Honest limitations still in force, by design:
- A remarketing "savings" figure is only ever computed when a remarket was
  genuinely initiated with a real carrier switch and both premiums are present.
  No workflow currently records a real carrier-switch decision, so today every
  live remarket outcome resolves to ``confirmation_value``/``not_remarketed``.
- Carrier performance groups by carrier NAME — the one consistent join key.
- Time-to-placement joins on submission_id — the same key used across MM, PA,
  QC, BI payloads for a single submission.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.admin.settings_override import get_effective_setting
from core.common.dtos import Ctx
from core.config import get_settings
from core.models import OutputPackage as OutputPackageRow
from core.models import PipelineStageEvent as StageEventRow


async def _payloads_for(session: AsyncSession, ctx: Ctx, workflow: str) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(OutputPackageRow).where(
                col(OutputPackageRow.tenant_id) == ctx.tenant_id,
                col(OutputPackageRow.workflow) == workflow,
            )
        )
    ).scalars().all()
    return [r.payload for r in rows if r.payload]


async def _rows_for(session: AsyncSession, ctx: Ctx, workflow: str) -> list[OutputPackageRow]:
    rows = (
        await session.execute(
            select(OutputPackageRow).where(
                col(OutputPackageRow.tenant_id) == ctx.tenant_id,
                col(OutputPackageRow.workflow) == workflow,
            )
        )
    ).scalars().all()
    return [r for r in rows if r.payload]


def _build_funnel_data(
    mm_rows: list[dict[str, Any]],
    pa_rows: list[dict[str, Any]],
    qc_rows: list[dict[str, Any]],
    bi_rows: list[dict[str, Any]],
) -> dict[str, int]:
    submissions_received = len(
        {r["submission_id"] for r in mm_rows if r.get("submission_id")}
    )
    matched_to_carrier = sum(1 for r in mm_rows if r.get("matches"))
    packages_assembled = len({
        r["submission_id"]
        for r in pa_rows
        if r.get("submission_id") and r.get("status") in ("READY", "READY_WITH_GAP")
    })
    quotes_received = len({
        r["submission_id"]
        for r in qc_rows
        if r.get("submission_id")
        and any(q.get("response_type") == "QUOTE" for q in r.get("quotes", []))
    })
    compared_and_selected = sum(1 for r in qc_rows if r.get("selected_quote_id"))
    bound = sum(1 for r in bi_rows if (r.get("carrier_confirmation") or {}).get("binder_number"))
    return {
        "submissions_received": submissions_received,
        "matched_to_carrier": matched_to_carrier,
        "packages_assembled": packages_assembled,
        "quotes_received": quotes_received,
        "compared_and_selected": compared_and_selected,
        "bound": bound,
    }


def _build_carrier_activity(
    pa_rows: list[dict[str, Any]], qc_rows: list[dict[str, Any]], bi_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    approached: dict[str, int] = defaultdict(int)
    quoted: dict[str, int] = defaultdict(int)
    binds: dict[str, int] = defaultdict(int)

    for r in pa_rows:
        name = r.get("carrier_name")
        if name:
            approached[name] += 1
    for r in qc_rows:
        for q in r.get("quotes", []):
            name = q.get("carrier_name")
            if name and q.get("response_type") == "QUOTE":
                quoted[name] += 1
    for r in bi_rows:
        name = r.get("carrier_name")
        if name and (r.get("carrier_confirmation") or {}).get("binder_number"):
            binds[name] += 1

    return [
        {
            "carrier_name": name,
            "submissions_approached": approached[name],
            "quotes_issued": quoted.get(name, 0),
            "binds": binds.get(name, 0),
        }
        for name in sorted(approached)  # approached > 0 for every key here, by construction
    ]


def _build_time_to_placement_data(
    mm_rows: list[OutputPackageRow], bi_rows: list[OutputPackageRow]
) -> list[dict[str, Any]]:
    """PR-03: raw elapsed time from a submission's earliest real Market
    Matching row to the real Binder Issuance row where it was actually
    bound (a real ``carrier_confirmation.binder_number`` on file) — joined
    by ``submission_id``.  ``submission_id`` is included in each placement
    dict so ``build_time_to_placement_carrier_attributed()`` can join with
    PipelineStageEvent rows (FR-4)."""
    matched_at: dict[str, Any] = {}
    for r in mm_rows:
        sub_id = (r.payload or {}).get("submission_id")
        if not sub_id:
            continue
        if sub_id not in matched_at or r.created_at < matched_at[sub_id]:
            matched_at[sub_id] = r.created_at

    placements: list[dict[str, Any]] = []
    for r in bi_rows:
        payload = r.payload or {}
        sub_id = payload.get("submission_id")
        carrier_name = payload.get("carrier_name")
        binder_number = (payload.get("carrier_confirmation") or {}).get("binder_number")
        if not sub_id or not carrier_name or not binder_number:
            continue
        start = matched_at.get(sub_id)
        if start is None:
            continue
        days = (r.created_at.date() - start.date()).days
        if days < 0:
            continue  # out-of-order/clock-skew data — never report a negative elapsed time
        placements.append({"carrier_name": carrier_name, "days": days, "submission_id": sub_id})
    return placements


def _extract_bound_premium(bi_payload: dict[str, Any]) -> float | None:
    """Extract the bound premium from a Binder Issuance payload.

    Prefers ``carrier_confirmation.confirmed_terms.premium`` (the confirmed
    carrier figure); falls back to ``requested_bind_terms.premium_estimate``
    (the broker's estimated figure at bind request time). Returns None if
    neither is present — never fabricates a figure (KB06)."""
    confirmed = (bi_payload.get("carrier_confirmation") or {}).get("confirmed_terms") or {}
    premium = confirmed.get("premium")
    if premium is not None:
        return float(premium)
    requested = bi_payload.get("requested_bind_terms") or {}
    estimate = requested.get("premium_estimate")
    if estimate is not None:
        return float(estimate)
    return None


def _build_bound_submissions_data(bi_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bound submissions with extractable premiums — input for revenue attribution (FR-6 / PR-04).

    Only rows with a real binder number (actually bound) and a real premium
    value are included. Submissions without a premium are excluded — never
    guessed (KB06)."""
    results = []
    for r in bi_rows:
        if not (r.get("carrier_confirmation") or {}).get("binder_number"):
            continue
        carrier_name = r.get("carrier_name")
        if not carrier_name:
            continue
        premium = _extract_bound_premium(r)
        if premium is None:
            continue
        results.append({"carrier_name": carrier_name, "bound_premium": premium})
    return results


def _build_remarket_outcomes(rr_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_account: dict[str, dict[str, Any]] = {}
    for r in rr_rows:
        name = r.get("named_insured") or "Unknown account"
        entry = by_account.setdefault(name, {})
        if r.get("is_comparison_stage"):
            entry["execution"] = r.get("remarket_execution") or {}
            entry["final_decision"] = r.get("final_decision") or {}
        else:
            trigger_decision = r.get("trigger_decision") or {}
            entry["trigger_level"] = trigger_decision.get("level", "NO_REMARKET")
            entry["reasoning_summary"] = (trigger_decision.get("reasoning") or {}).get("summary")

    outcomes = []
    for name, entry in by_account.items():
        trigger = entry.get("trigger_level", "NO_REMARKET")
        execution = entry.get("execution") or {}
        comparison = execution.get("comparison_output") or {}
        final = entry.get("final_decision") or {}

        savings: float | None = None
        if (
            trigger != "NO_REMARKET"
            and execution.get("initiated")
            and final.get("outcome") == "switched_carrier"
            and comparison.get("directly_comparable")
        ):
            incumbent_premium = (comparison.get("incumbent") or {}).get("premium")
            alternative_premium = (comparison.get("alternative") or {}).get("premium")
            if incumbent_premium is not None and alternative_premium is not None:
                savings = incumbent_premium - alternative_premium

        outcomes.append({
            "account": name,
            "trigger": trigger.lower(),
            "savings_identified": savings,
            "note": entry.get("reasoning_summary"),
        })
    return outcomes


async def _load_stage_events(session: AsyncSession, ctx: Ctx) -> list[dict[str, Any]]:
    """Load all PipelineStageEvent rows for this tenant as plain dicts.

    Returns empty list if the table is empty (no live packages have been
    assembled yet) — callers must handle this gracefully (FR-4 section
    is omitted from the report when no events exist)."""
    rows = (
        await session.execute(
            select(StageEventRow).where(
                col(StageEventRow.tenant_id) == ctx.tenant_id
            )
        )
    ).scalars().all()
    return [
        {
            "submission_ref": r.submission_ref,
            "stage": r.stage,
            "entered_at": r.entered_at,
            "exited_at": r.exited_at,
            "attribution": r.attribution,
        }
        for r in rows
    ]


def _load_commission_config(tenant_id: str) -> dict[str, float]:
    """Load the commission-rate config for this tenant.

    Per-tenant override via Admin Panel key ``commission_rates_json`` (JSON
    object string) takes precedence; falls back to the global
    ``Settings.commission_rates_json`` env var.  Returns empty dict if
    neither is set or the JSON is invalid — the reporting engine then marks
    every carrier "not_configured" (KB06)."""
    from verticals.es.workflows.pipeline_reporting.reporting_engine import parse_commission_config  # lazy import avoids circular
    raw = get_effective_setting(tenant_id, "commission_rates_json", get_settings().commission_rates_json)
    return parse_commission_config(str(raw))


async def build_live_underlying_data(session: AsyncSession, ctx: Ctx) -> dict[str, Any]:
    """The live-data equivalent of ``scenario_loader.load_scenario()``'s
    ``underlying_data.json`` shape, built from real cross-workflow rows.
    Unlike a single fixture scenario (which always exercises exactly one
    report "kind"), this returns funnel + carrier + time-to-placement +
    stage-events + revenue-attribution + remarketing data all at once."""
    mm_rows_raw = await _rows_for(session, ctx, "market_matching")
    bi_rows_raw = await _rows_for(session, ctx, "binder_issuance")
    mm_rows = [r.payload for r in mm_rows_raw]
    pa_rows = await _payloads_for(session, ctx, "package_assembly")
    qc_rows = await _payloads_for(session, ctx, "quote_comparison")
    bi_rows = [r.payload for r in bi_rows_raw]
    rr_rows = await _payloads_for(session, ctx, "renewal_remarketing")
    stage_events = await _load_stage_events(session, ctx)
    commission_config = _load_commission_config(ctx.tenant_id)

    return {
        **_build_funnel_data(mm_rows, pa_rows, qc_rows, bi_rows),
        "carrier_activity": _build_carrier_activity(pa_rows, qc_rows, bi_rows),
        "placements": _build_time_to_placement_data(mm_rows_raw, bi_rows_raw),
        "stage_events": stage_events,
        "bound_submissions": _build_bound_submissions_data(bi_rows),
        "commission_config": commission_config,
        "remarket_outcomes": _build_remarket_outcomes(rr_rows),
    }
