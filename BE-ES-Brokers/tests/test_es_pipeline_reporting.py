"""E&S Pipeline & Carrier Performance Reporting eval test — proves the
pipeline + router against the REAL Workflow_19 dataset (originally
``Data sets/Workflow_19/test_dataset``, copied to
``TEST_DATA_ROOT/Workflow_19/test_dataset`` per DATA_AND_FIXTURES.md).

Pytest-discovered here (not under src/verticals/es/...) — see
verticals/es/workflows/pipeline_reporting/eval_test.py for why.

Scenario 03 is the release-gate proof for this workflow: a logging gap
must never be silently interpolated or omitted. Scenario 02 proves a
low-volume carrier figure is never ranked/presented as equally reliable.
Scenario 04 proves a $0-savings confirmation never reads as a failure.

FR-4 delay exclusion (test_fr4_*) and FR-6 revenue attribution
(test_fr6_*) tests use synthetic in-memory DB data only — no
TEST_DATA_ROOT required. The _needs_fixtures marker gates only the
Workflow_19-fixture-based scenario tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from fixtures.loader import dataset_dir as _bundled_dataset_dir
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import core.models  # noqa: F401  (registers tables)
from core.admin.settings_override import clear_override, set_override
from core.common.dtos import Ctx, WorkflowInput
from core.common.enums import DecisionOutcome, Role, Vertical
from core.config import get_settings
from core.llm import build_llm_service
from core.models import OutputPackage as OutputPackageRow
from core.models import PipelineStageEvent as StageEventRow
from core.models import Tenant
from verticals.es.workflows.pipeline_reporting.router import (
    RunRequest,
    run_pipeline_reporting,
    run_pipeline_reporting_live,
)
from verticals.es.workflows.pipeline_reporting.service import PipelineReportingPipeline

# Applied individually to tests that need Workflow_19 fixture files.
# Live-path tests (es_session + synthetic rows) do NOT carry this mark
# and always run.
_needs_fixtures = pytest.mark.skipif(
    _bundled_dataset_dir(19) is None,
    reason="Workflow_19 fixture dataset not found (TEST_DATA_ROOT or bundled Data sets)",
)


@pytest.fixture
def es_ctx() -> Ctx:
    return Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u-jr", role=Role.JUNIOR)


@pytest.fixture
async def es_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add(Tenant(id="demo-es", name="Demo E&S", vertical=Vertical.ES))
        await session.commit()
        yield session
    await engine.dispose()


def _pipeline() -> PipelineReportingPipeline:
    return PipelineReportingPipeline(llm=build_llm_service())


async def _run(ctx: Ctx, scenario_ref: str):
    pipeline = _pipeline()
    return await pipeline.run(ctx, WorkflowInput(source_ref=scenario_ref))


@_needs_fixtures
async def test_scenario_01_clean_funnel_baseline(es_ctx) -> None:
    output = await _run(es_ctx, "scenario_01")
    payload = output.payload
    assert payload["data_completeness"]["status"] == "COMPLETE"
    assert output.decision.outcome is DecisionOutcome.PROCEED
    stages = {s["stage"]: s for s in payload["funnel"]}
    assert stages["Bound"]["count"] == 47
    assert stages["Bound"]["pct_of_prior_stage"] == 81.0
    # 47/84 = 55.952...% -> rounds to 56.0 (the dataset's own prose says "55.9%",
    # a minor hand-authoring imprecision — illustrative text, not a literal
    # assertion target, same precedent as every prior workflow's expected_output).
    assert payload["overall_conversion_pct"] == 56.0


@_needs_fixtures
async def test_scenario_02_low_volume_carrier_annotated_and_ordered(es_ctx) -> None:
    output = await _run(es_ctx, "scenario_02")
    payload = output.payload
    carriers = payload["carrier_performance"]
    # Ordered by volume, NOT by hit-rate — Ironclad (22) must come before
    # Vantage (4) even though Vantage's raw rate is higher.
    assert [c["carrier_name"] for c in carriers] == [
        "Ironclad Casualty Solutions", "Vantage Excess Partners",
    ]
    ironclad, vantage = carriers
    assert ironclad["overall_hit_rate"] == 63.6
    assert ironclad["low_volume_flag"] is False
    assert vantage["overall_hit_rate"] == 100.0
    assert vantage["low_volume_flag"] is True


@_needs_fixtures
async def test_scenario_03_data_gap_never_interpolated(es_ctx) -> None:
    """RELEASE GATE: the gapped stage's own figure AND the following
    stage's percentage must both be explicitly withheld — never
    estimated — while the following stage's raw count still shows since
    its own logging is unaffected."""
    output = await _run(es_ctx, "scenario_03")
    payload = output.payload
    assert payload["data_completeness"]["status"] == "PARTIAL"
    assert output.decision.outcome is DecisionOutcome.REQUEST_INFO
    gaps = payload["data_completeness"]["gaps"]
    assert any(g["stage"] == "Compared & Selected" for g in gaps)

    stages = {s["stage"]: s for s in payload["funnel"]}
    assert stages["Compared & Selected"]["count"] is None
    assert stages["Compared & Selected"]["pct_of_prior_stage"] is None
    assert stages["Bound"]["count"] == 47  # bind logging itself unaffected
    assert stages["Bound"]["pct_of_prior_stage"] is None  # denominator unknown

    # Never silently smoothed into a clean top-line figure either.
    assert payload["overall_conversion_pct"] is None


@_needs_fixtures
async def test_scenario_04_confirmation_value_not_a_failure(es_ctx) -> None:
    output = await _run(es_ctx, "scenario_04")
    payload = output.payload
    outcomes = {o["account"]: o for o in payload["remarketing_value"]}

    summit = outcomes["Summit Roofing Group"]
    assert summit["outcome_type"] == "confirmation_value"
    assert summit["savings_amount"] is None

    clearpath = outcomes["Clearpath Bookkeeping (prior 2 cycles)"]
    assert clearpath["outcome_type"] == "not_remarketed"
    assert clearpath["savings_amount"] is None


@_needs_fixtures
async def test_run_endpoint(es_ctx, es_session) -> None:
    body = RunRequest(scenario_ref="scenario_01")
    item = await run_pipeline_reporting(body, es_ctx, es_session)
    assert item.status == "pending"
    assert item.payload.period == "Q3 2027"


async def test_run_live_aggregates_real_cross_workflow_rows(es_ctx, es_session) -> None:
    """The additive live-aggregation path (PR-01's real cross-workflow
    read): inserts real OutputPackage rows directly (same shape each real
    workflow's own service.py produces) across market_matching,
    package_assembly, quote_comparison, binder_issuance, and
    renewal_remarketing, then confirms /run-live builds a genuine report
    from them — never from the Workflow_19 fixture."""
    rows = [
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-P1", workflow="market_matching",
            payload={
                "submission_id": "SUB-P1",
                "matches": [{"carrier_id": "CAR-IC", "carrier_name": "Ironclad", "score": 82.0}],
                "excluded": [], "diligent_search": {
                    "required": False, "on_file": 0, "compliant": True, "note": "n/a",
                },
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-P2", workflow="market_matching",
            payload={
                "submission_id": "SUB-P2", "matches": [], "excluded": [],
                "diligent_search": {
                    "required": False, "on_file": 0, "compliant": True, "note": "n/a",
                },
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-P1", workflow="package_assembly",
            payload={
                "package_id": "PKG-1", "submission_id": "SUB-P1", "carrier_id": "CAR-IC",
                "carrier_name": "Ironclad", "status": "READY",
                "cover_letter": {"body": "...", "citations": []},
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-P1", workflow="package_assembly",
            payload={
                "package_id": "PKG-2", "submission_id": "SUB-P1", "carrier_id": "CAR-VT",
                "carrier_name": "Vantage", "status": "READY",
                "cover_letter": {"body": "...", "citations": []},
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-P1", workflow="quote_comparison",
            payload={
                "submission_id": "SUB-P1",
                "quotes": [
                    {
                        "quote_id": "Q-IC", "submission_id": "SUB-P1", "carrier_name": "Ironclad",
                        "response_type": "QUOTE",
                    },
                    {
                        "quote_id": "Q-VT", "submission_id": "SUB-P1", "carrier_name": "Vantage",
                        "response_type": "DECLINATION",
                    },
                ],
                "comparability_assessment": {"directly_comparable": True, "material_differences": []},
                "output_mode": "SINGLE_RECOMMENDATION",
                "recommendation": {"reasoning": {"summary": "..."}},
                "selected_quote_id": "Q-IC",
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-P1", workflow="binder_issuance",
            payload={
                "bind_id": "BIND-1", "submission_id": "SUB-P1", "carrier_id": "CAR-IC",
                "carrier_name": "Ironclad", "requested_bind_terms": {},
                "carrier_confirmation": {"binder_number": "BINDER-123"},
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="RR-1", workflow="renewal_remarketing",
            payload={
                "renewal_review_id": "RR-1", "named_insured": "Some Account",
                "is_comparison_stage": False,
                "trigger_decision": {
                    "level": "FULL_REMARKET",
                    "reasoning": {"summary": "Adverse pricing vs. exposure change."},
                },
            },
        ),
    ]
    es_session.add_all(rows)
    await es_session.commit()

    item = await run_pipeline_reporting_live(es_ctx, es_session)
    payload = item.payload

    stages = {s.stage: s for s in payload.funnel}
    assert stages["Submissions Received"].count == 2
    assert stages["Matched to Carrier"].count == 1
    assert stages["Packages Assembled"].count == 1
    assert stages["Quotes Received"].count == 1
    assert stages["Compared & Selected"].count == 1
    assert stages["Bound"].count == 1
    assert payload.data_completeness.status == "COMPLETE"

    carriers = {c.carrier_name: c for c in payload.carrier_performance}
    assert carriers["Ironclad"].submissions_approached == 1
    assert carriers["Ironclad"].quote_rate == 100.0
    assert carriers["Ironclad"].overall_hit_rate == 100.0
    assert carriers["Ironclad"].low_volume_flag is True  # 1 < the placeholder threshold
    assert carriers["Vantage"].quote_rate == 0.0

    outcome = payload.remarketing_value[0]
    assert outcome.account == "Some Account"
    # No workflow anywhere records a real carrier-switch decision yet, so a
    # remarket that was triggered but never confirmed switched honestly
    # produces confirmation_value, never a guessed savings figure.
    assert outcome.outcome_type == "confirmation_value"
    assert outcome.savings_amount is None


async def test_run_live_time_to_placement_is_raw_elapsed_days(es_ctx, es_session) -> None:
    """Gap-fill (PR-03/FR-4): real elapsed time from a submission's
    earliest Market Matching row to its Binder Issuance bind, per carrier
    — joined by submission_id, the same real join key funnel counting
    already relies on. FR-4's broker/agent-delay exclusion is honestly
    NOT applied (Package Assembly has no history of BLOCKED-status
    duration to compute it from) — this proves the raw elapsed-day math
    itself is correct and grounded in real timestamps, never fabricated."""
    matched_at = datetime(2027, 6, 1, 12, 0, tzinfo=UTC)
    bound_at = matched_at + timedelta(days=14)

    rows = [
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-T1", workflow="market_matching",
            created_at=matched_at,
            payload={
                "submission_id": "SUB-T1",
                "matches": [{"carrier_id": "CAR-IC", "carrier_name": "Ironclad", "score": 82.0}],
                "excluded": [],
                "diligent_search": {"required": False, "on_file": 0, "compliant": True, "note": "n/a"},
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-T1", workflow="binder_issuance",
            created_at=bound_at,
            payload={
                "bind_id": "BIND-T1", "submission_id": "SUB-T1", "carrier_id": "CAR-IC",
                "carrier_name": "Ironclad", "requested_bind_terms": {},
                "carrier_confirmation": {"binder_number": "BINDER-T1"},
            },
        ),
    ]
    es_session.add_all(rows)
    await es_session.commit()

    item = await run_pipeline_reporting_live(es_ctx, es_session)
    payload = item.payload

    placement = next(p for p in payload.time_to_placement if p.carrier_name == "Ironclad")
    assert placement.submissions_bound == 1
    assert placement.avg_days == 14.0
    assert placement.delay_excluded is False  # honest — FR-4's exclusion is not computed


# ── FR-4 delay exclusion ─────────────────────────────────────────────────────

async def test_fr4_delay_excluded_carrier_attributed_vs_raw(
    es_ctx: Ctx, es_session: AsyncSession,
) -> None:
    """FR-4: two submissions in one batch run:

    Case A (SUB-D1 / Ironclad):
        raw_elapsed = 21 days
        BLOCKED span attributed BROKER = 7 days  (days 4–11 of the window)
        carrier_attributed = 21 − 7 = 14 days

    Case B (SUB-D2 / Vantage):
        raw_elapsed = 10 days
        NO BLOCKED span recorded
        carrier_attributed = 10 days  (identical to raw; zero broker delay)

    Because stage_events exist (for SUB-D1), ``time_to_placement_carrier_attributed``
    is populated for BOTH carriers and ``delay_excluded=True`` on the raw
    TimeToPlacementOut rows as well (the signal "a carrier-attributed figure
    is available alongside this raw number").
    """
    matched_at = datetime(2027, 5, 1, 8, 0, tzinfo=UTC)
    # Case A
    bound_d1 = matched_at + timedelta(days=21)
    blocked_enter = matched_at + timedelta(days=4)
    blocked_exit = matched_at + timedelta(days=11)   # 7 broker days
    # Case B
    bound_d2 = matched_at + timedelta(days=10)

    rows = [
        # Market Matching — both submissions matched
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-D1",
            workflow="market_matching", created_at=matched_at,
            payload={
                "submission_id": "SUB-D1",
                "matches": [{"carrier_id": "CAR-IC", "carrier_name": "Ironclad", "score": 88.0}],
                "excluded": [],
                "diligent_search": {"required": False, "on_file": 0, "compliant": True, "note": "n/a"},
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-D2",
            workflow="market_matching", created_at=matched_at,
            payload={
                "submission_id": "SUB-D2",
                "matches": [{"carrier_id": "CAR-VT", "carrier_name": "Vantage", "score": 72.0}],
                "excluded": [],
                "diligent_search": {"required": False, "on_file": 0, "compliant": True, "note": "n/a"},
            },
        ),
        # Binder Issuance — both bound
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-D1",
            workflow="binder_issuance", created_at=bound_d1,
            payload={
                "bind_id": "BIND-D1", "submission_id": "SUB-D1",
                "carrier_id": "CAR-IC", "carrier_name": "Ironclad",
                "requested_bind_terms": {},
                "carrier_confirmation": {"binder_number": "BINDER-D1"},
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-D2",
            workflow="binder_issuance", created_at=bound_d2,
            payload={
                "bind_id": "BIND-D2", "submission_id": "SUB-D2",
                "carrier_id": "CAR-VT", "carrier_name": "Vantage",
                "requested_bind_terms": {},
                "carrier_confirmation": {"binder_number": "BINDER-D2"},
            },
        ),
    ]
    # BLOCKED span for SUB-D1 only — broker was assembling docs for 7 days
    stage_event = StageEventRow(
        id=str(uuid4()),
        tenant_id=es_ctx.tenant_id,
        submission_ref="SUB-D1",
        stage="package_assembly_blocked",
        entered_at=blocked_enter,
        exited_at=blocked_exit,
        attribution="BROKER",
    )
    es_session.add_all(rows)
    es_session.add(stage_event)
    await es_session.commit()

    item = await run_pipeline_reporting_live(es_ctx, es_session)
    payload = item.payload

    # ── carrier-attributed section present (stage events exist) ──────────────
    ca = {p.carrier_name: p for p in payload.time_to_placement_carrier_attributed}
    assert "Ironclad" in ca, "Ironclad must appear in carrier-attributed section"
    assert "Vantage" in ca, "Vantage must appear in carrier-attributed section"

    ic = ca["Ironclad"]
    vt = ca["Vantage"]

    # Case A: 7 broker days subtracted
    assert ic.avg_days_raw == 21.0, f"Ironclad raw should be 21, got {ic.avg_days_raw}"
    assert ic.avg_days_carrier_attributed == 14.0, (
        f"Ironclad carrier_attributed should be 14 (21−7), got {ic.avg_days_carrier_attributed}"
    )

    # Case B: no BLOCKED span — carrier_attributed identical to raw
    assert vt.avg_days_raw == 10.0, f"Vantage raw should be 10, got {vt.avg_days_raw}"
    assert vt.avg_days_carrier_attributed == 10.0, (
        f"Vantage carrier_attributed should equal raw (10) when no span recorded, "
        f"got {vt.avg_days_carrier_attributed}"
    )

    # ── raw section still present; delay_excluded=True signals CA is available ─
    raw = {p.carrier_name: p for p in payload.time_to_placement}
    assert raw["Ironclad"].avg_days == 21.0
    assert raw["Vantage"].avg_days == 10.0
    assert raw["Ironclad"].delay_excluded is True, "delay_excluded must be True when CA data present"
    assert raw["Vantage"].delay_excluded is True


async def test_fr4_open_blocked_span_never_subtracted(
    es_ctx: Ctx, es_session: AsyncSession,
) -> None:
    """FR-4 / KB06: an open BLOCKED span (exited_at is None) is never subtracted
    — subtracting an unknown duration would fabricate a figure. The raw elapsed
    time is returned unchanged as the carrier-attributed figure."""
    matched_at = datetime(2027, 5, 15, 8, 0, tzinfo=UTC)
    bound_at = matched_at + timedelta(days=14)

    rows = [
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-O1",
            workflow="market_matching", created_at=matched_at,
            payload={
                "submission_id": "SUB-O1",
                "matches": [{"carrier_id": "CAR-IC", "carrier_name": "Ironclad", "score": 80.0}],
                "excluded": [],
                "diligent_search": {"required": False, "on_file": 0, "compliant": True, "note": "n/a"},
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-O1",
            workflow="binder_issuance", created_at=bound_at,
            payload={
                "bind_id": "BIND-O1", "submission_id": "SUB-O1",
                "carrier_id": "CAR-IC", "carrier_name": "Ironclad",
                "requested_bind_terms": {},
                "carrier_confirmation": {"binder_number": "BINDER-O1"},
            },
        ),
    ]
    # Open span — exited_at is None (submission still BLOCKED right now)
    open_span = StageEventRow(
        id=str(uuid4()),
        tenant_id=es_ctx.tenant_id,
        submission_ref="SUB-O1",
        stage="package_assembly_blocked",
        entered_at=matched_at + timedelta(days=2),
        exited_at=None,   # open — must NOT be subtracted
        attribution="BROKER",
    )
    es_session.add_all(rows)
    es_session.add(open_span)
    await es_session.commit()

    item = await run_pipeline_reporting_live(es_ctx, es_session)
    payload = item.payload

    ca = {p.carrier_name: p for p in payload.time_to_placement_carrier_attributed}
    assert "Ironclad" in ca
    ic = ca["Ironclad"]
    # open span contributes zero — attributed must equal raw
    assert ic.avg_days_raw == 14.0
    assert ic.avg_days_carrier_attributed == 14.0, (
        f"Open span must not be subtracted; expected 14.0, got {ic.avg_days_carrier_attributed}"
    )


# ── FR-6 revenue attribution ─────────────────────────────────────────────────

async def test_fr6_revenue_with_commission_config(
    es_ctx: Ctx, es_session: AsyncSession,
) -> None:
    """FR-6: with commission config present, revenue == bound_premium × rate.
    Every figure carries provisional=True; not_configured=False."""
    bound_at = datetime(2027, 6, 1, 12, 0, tzinfo=UTC)
    matched_at = bound_at - timedelta(days=14)

    rows = [
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-R1",
            workflow="market_matching", created_at=matched_at,
            payload={
                "submission_id": "SUB-R1",
                "matches": [{"carrier_id": "CAR-IC", "carrier_name": "Ironclad", "score": 85.0}],
                "excluded": [],
                "diligent_search": {"required": False, "on_file": 0, "compliant": True, "note": "n/a"},
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-R1",
            workflow="binder_issuance", created_at=bound_at,
            payload={
                "bind_id": "BIND-R1", "submission_id": "SUB-R1",
                "carrier_id": "CAR-IC", "carrier_name": "Ironclad",
                "requested_bind_terms": {},
                "carrier_confirmation": {
                    "binder_number": "BINDER-R1",
                    "confirmed_terms": {"premium": 50000},
                },
            },
        ),
    ]
    es_session.add_all(rows)
    await es_session.commit()

    # Inject per-tenant commission config (12 % for Ironclad)
    set_override(es_ctx.tenant_id, "commission_rates_json", '{"Ironclad": 0.12}')
    try:
        item = await run_pipeline_reporting_live(es_ctx, es_session)
    finally:
        clear_override(es_ctx.tenant_id, "commission_rates_json")

    payload = item.payload

    assert len(payload.revenue_attribution) == 1, (
        f"Expected 1 revenue entry, got {len(payload.revenue_attribution)}"
    )
    rev = payload.revenue_attribution[0]
    assert rev.carrier_name == "Ironclad"
    assert rev.submissions_bound == 1
    assert rev.bound_premium_total == 50000.0
    assert rev.commission_rate == 0.12
    # revenue == Σ(bound_premium × rate) = 50 000 × 0.12 = 6 000
    assert rev.estimated_commission == 6000.0, (
        f"Expected estimated_commission=6000.0, got {rev.estimated_commission}"
    )
    assert rev.not_configured is False
    assert rev.provisional is True, "Every revenue figure must carry provisional=True"


async def test_fr6_revenue_no_commission_config_shows_not_configured(
    es_ctx: Ctx, es_session: AsyncSession,
) -> None:
    """FR-6 / KB06: without a commission config the tile shows 'not_configured'
    and NEVER emits a guessed figure. The report still generates (no crash,
    no empty payload)."""
    bound_at = datetime(2027, 6, 1, 12, 0, tzinfo=UTC)
    matched_at = bound_at - timedelta(days=14)

    rows = [
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-NC1",
            workflow="market_matching", created_at=matched_at,
            payload={
                "submission_id": "SUB-NC1",
                "matches": [{"carrier_id": "CAR-IC", "carrier_name": "Ironclad", "score": 85.0}],
                "excluded": [],
                "diligent_search": {"required": False, "on_file": 0, "compliant": True, "note": "n/a"},
            },
        ),
        OutputPackageRow(
            tenant_id=es_ctx.tenant_id, submission_id="SUB-NC1",
            workflow="binder_issuance", created_at=bound_at,
            payload={
                "bind_id": "BIND-NC1", "submission_id": "SUB-NC1",
                "carrier_id": "CAR-IC", "carrier_name": "Ironclad",
                "requested_bind_terms": {},
                "carrier_confirmation": {
                    "binder_number": "BINDER-NC1",
                    "confirmed_terms": {"premium": 50000},
                },
            },
        ),
    ]
    es_session.add_all(rows)
    await es_session.commit()

    # No commission config — default commission_rates_json is "{}" (empty)
    # Ensure no leftover override from another test contaminates this run
    clear_override(es_ctx.tenant_id, "commission_rates_json")

    item = await run_pipeline_reporting_live(es_ctx, es_session)
    payload = item.payload

    # Report must still generate
    assert payload is not None

    # Revenue entry still present (carrier has bound submissions), but no figure
    assert len(payload.revenue_attribution) == 1, (
        f"Expected 1 revenue entry even without config; got {len(payload.revenue_attribution)}"
    )
    rev = payload.revenue_attribution[0]
    assert rev.not_configured is True, "Carrier without rate must show not_configured=True"
    assert rev.estimated_commission is None, (
        f"No commission figure must be emitted; got {rev.estimated_commission}"
    )
    # provisional remains True — the absence of a figure is itself a proviso
    assert rev.provisional is True


# ── No-regression: Scenario 04 + Scenario 03 with new-metric assertions ──────

@_needs_fixtures
async def test_scenario_04_no_regression_new_metrics_absent(es_ctx: Ctx) -> None:
    """No-regression: Scenario 04 ($0-savings / confirmation_value) still
    distinguishes savings_identified from confirmation_value, AND the new
    FR-4 / FR-6 fields are explicitly empty (the remarketing fixture has no
    stage events and no bound-premium data — they must never be interpolated
    or guessed from remarketing rows alone)."""
    output = await _run(es_ctx, "scenario_04")
    payload = output.payload

    # ── original assertions still hold ───────────────────────────────────────
    outcomes = {o["account"]: o for o in payload["remarketing_value"]}

    summit = outcomes["Summit Roofing Group"]
    assert summit["outcome_type"] == "confirmation_value"
    assert summit["savings_amount"] is None

    clearpath = outcomes["Clearpath Bookkeeping (prior 2 cycles)"]
    assert clearpath["outcome_type"] == "not_remarketed"
    assert clearpath["savings_amount"] is None

    # ── new FR-4 / FR-6 metrics: absent, not interpolated ────────────────────
    # Remarketing fixture has no placements or stage events — the carrier-
    # attributed section must be empty, never fabricated from remarket rows.
    assert payload["time_to_placement_carrier_attributed"] == [], (
        "FR-4 carrier-attributed section must be empty for a remarketing fixture "
        "(no stage events, no bound submissions recorded in this scenario)"
    )
    # No commission config was supplied and no bound premiums exist in the
    # remarketing fixture — revenue_attribution must be empty, not guessed.
    assert payload["revenue_attribution"] == [], (
        "FR-6 revenue_attribution must be empty for a remarketing fixture "
        "(no carrier_confirmation rows with premiums)"
    )


@_needs_fixtures
async def test_scenario_03_fr2_gap_new_metrics_not_interpolated(es_ctx: Ctx) -> None:
    """FR-2 gap period: the gap is displayed; the new FR-4 and FR-6 metrics are
    NOT interpolated across the gap period.

    Scenario 03 is a funnel report with a logging gap in 'Compared & Selected'.
    The fixture carries no stage_events and no bound_submissions with premiums,
    so the carrier-attributed and revenue sections must be empty — never
    synthesised from funnel row counts (which would be fabrication)."""
    output = await _run(es_ctx, "scenario_03")
    payload = output.payload

    # ── gap still displayed ───────────────────────────────────────────────────
    assert payload["data_completeness"]["status"] == "PARTIAL"
    gaps = payload["data_completeness"]["gaps"]
    assert any(g["stage"] == "Compared & Selected" for g in gaps), (
        "Gap must still be surfaced after FR-4 / FR-6 code added"
    )
    stages = {s["stage"]: s for s in payload["funnel"]}
    assert stages["Compared & Selected"]["count"] is None
    assert stages["Compared & Selected"]["pct_of_prior_stage"] is None

    # ── new metrics NOT interpolated ──────────────────────────────────────────
    # The gap in Compared & Selected must not be smoothed into the new sections.
    # carrier_attributed relies on PipelineStageEvent rows that don't exist in
    # the fixture — it must be empty, not estimated from funnel deltas.
    assert payload["time_to_placement_carrier_attributed"] == [], (
        "Carrier-attributed timing must not be interpolated across a data-gap period"
    )
    # No bound premiums in the funnel fixture — revenue must not be fabricated.
    assert payload["revenue_attribution"] == [], (
        "Revenue attribution must not be guessed from a partial-funnel scenario"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PR-02/FR-3: distinct-submission carrier counting + >100% rate guard
# ═══════════════════════════════════════════════════════════════════════════════


def test_carrier_activity_counts_distinct_submissions_not_line_items() -> None:
    """A carrier quoted twice for the same submission (original quote AND a
    renewal-offer quote in a second comparison record) counts ONCE — so its
    quote rate can never exceed 100%."""
    from verticals.es.workflows.pipeline_reporting.live_aggregator import (
        _build_carrier_activity,
    )
    from verticals.es.workflows.pipeline_reporting.reporting_engine import (
        build_carrier_performance,
    )

    pa_rows = [{"submission_id": "SUB-1", "carrier_name": "Ironclad"}]
    qc_rows = [
        {
            "submission_id": "SUB-1",
            "quotes": [{"carrier_name": "Ironclad", "response_type": "QUOTE"}],
        },
        {  # renewal-offer comparison for the SAME submission — must not double-count
            "submission_id": "SUB-1",
            "quotes": [{"carrier_name": "Ironclad", "response_type": "QUOTE"}],
        },
    ]
    bi_rows = [
        {
            "submission_id": "SUB-1",
            "carrier_name": "Ironclad",
            "carrier_confirmation": {"binder_number": "BN-1"},
        }
    ]

    activity = _build_carrier_activity(pa_rows, qc_rows, bi_rows)
    assert activity == [
        {
            "carrier_name": "Ironclad",
            "submissions_approached": 1,
            "quotes_issued": 1,
            "binds": 1,
        }
    ]

    perf = build_carrier_performance(activity, min_reliable_volume=1)
    assert perf[0].quote_rate == 100.0
    assert perf[0].bind_rate == 100.0
    assert perf[0].overall_hit_rate == 100.0


def test_carrier_performance_guard_rejects_rate_above_100() -> None:
    """If upstream counting ever regresses to raw line items, the engine fails
    loudly instead of publishing an impossible >100% rate (PR-02/FR-3)."""
    from verticals.es.workflows.pipeline_reporting.reporting_engine import (
        build_carrier_performance,
    )

    bad_activity = [
        {"carrier_name": "Ironclad", "submissions_approached": 1, "quotes_issued": 2, "binds": 1}
    ]
    with pytest.raises(ValueError, match="above 100%"):
        build_carrier_performance(bad_activity, min_reliable_volume=1)
