"""E&S Diligent Search & Compliance Documentation eval test — proves the
pipeline + router against the REAL Workflow_17 dataset (originally
``Data sets/Workflow_17/test_dataset``, copied to
``TEST_DATA_ROOT/Workflow_17/test_dataset`` per DATA_AND_FIXTURES.md).

Pytest-discovered here (not under src/verticals/es/...) — see
verticals/es/workflows/diligent_search/eval_test.py for why.

Scenario 03 is the mandatory, non-skippable release gate for this
workflow (PRD §2.3/§8): zero non-compliant document generation is the
highest-stakes success criterion in the entire vertical.
"""

from __future__ import annotations

import pytest

from fixtures.loader import dataset_dir as _bundled_dataset_dir
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, col, select

import core.models  # noqa: F401  (registers tables)
from core.common.dtos import Ctx, WorkflowInput
from core.common.enums import DecisionOutcome, ReviewStatus, Role, Vertical
from core.config import get_settings
from core.llm import build_llm_service
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.models import StateRetentionReference as StateRetentionReferenceRow
from core.models import Tenant
from verticals.es.workflows.diligent_search.compliance_engine import determine_state
from verticals.es.workflows.diligent_search.router import (
    LiveDeclinationInput,
    LiveStateInput,
    RunLiveRequest,
    RunRequest,
    approve,
    escalate,
    list_live_submissions,
    run_diligent_search,
    run_diligent_search_live,
)
from verticals.es.workflows.diligent_search.service import DiligentSearchPipeline
from verticals.es.workflows.market_matching.router import (
    RunRequest as MarketMatchingRunRequest,
)
from verticals.es.workflows.market_matching.router import run_market_matching

# Applied individually — FR-8 unit tests run without TEST_DATA_ROOT.
_needs_fixtures = pytest.mark.skipif(
    _bundled_dataset_dir(17) is None,
    reason="Workflow_17 fixture dataset not found (TEST_DATA_ROOT or bundled Data sets)",
)


@pytest.fixture
def es_ctx() -> Ctx:
    return Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u-jr", role=Role.JUNIOR)


@pytest.fixture
def es_ctx_senior() -> Ctx:
    return Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u-sr", role=Role.SENIOR)


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


@pytest.fixture
def mock_connectors_mode(monkeypatch):
    """Seeding a real MM-07 stub only needs Market Matching's own fixture
    path (``submission_ref``), same as ``test_zero_match_seeds_diligent_
    search_stub`` in test_es_market_matching.py — forces mock mode for this
    setup step regardless of the environment's own CONNECTORS_MODE, so
    these tests aren't at the mercy of a real (unmocked) Nango call."""
    monkeypatch.setenv("CONNECTORS_MODE", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _pipeline() -> DiligentSearchPipeline:
    return DiligentSearchPipeline(llm=build_llm_service())


async def _run(ctx: Ctx, scenario_ref: str):
    pipeline = _pipeline()
    return await pipeline.run(ctx, WorkflowInput(source_ref=scenario_ref))


@_needs_fixtures
async def test_scenario_01_ready_sufficient_evidence(es_ctx) -> None:
    """3 of 3 required declinations on file, all written — a compliant
    document is generated, grounded only in the actual declination
    records."""
    output = await _run(es_ctx, "scenario_01")
    payload = output.payload
    assert payload["overall_status"] == "COMPLETE"
    assert output.decision.outcome is DecisionOutcome.PROCEED
    state = payload["state_determinations"][0]
    assert state["state"] == "Oregon"
    assert state["requirement_status"] == "REQUIRED"
    assert state["sufficiency_status"] == "SUFFICIENT"
    assert state["document_generated"] is True
    assert state["generated_document_text"]
    assert len(state["declinations_on_file"]) == 3


@_needs_fixtures
async def test_scenario_02_exempt_explicitly_logged(es_ctx) -> None:
    """Export-list exemption must be its own distinct, explicitly-logged
    determination — never indistinguishable from "missing documentation"."""
    output = await _run(es_ctx, "scenario_02")
    payload = output.payload
    assert payload["overall_status"] == "COMPLETE"
    state = payload["state_determinations"][0]
    assert state["state"] == "Texas"
    assert state["requirement_status"] == "EXEMPT"
    assert state["exemption_basis"] is not None and "export list" in state["exemption_basis"]
    assert state["sufficiency_status"] == "NOT_APPLICABLE"
    assert state["document_generated"] is False
    assert state["generated_document_text"] is None


@_needs_fixtures
async def test_scenario_03_blocked_insufficient_evidence_no_document(es_ctx) -> None:
    """RELEASE GATE: only 2 of 3 declinations on file, one verbal-only.
    Must BLOCK and generate ZERO document text — a wrong affidavit here
    would be a potentially fraudulent record, the PRD's own top risk."""
    output = await _run(es_ctx, "scenario_03")
    payload = output.payload
    assert payload["overall_status"] == "BLOCKED"
    assert output.decision.outcome is DecisionOutcome.REQUEST_INFO
    state = payload["state_determinations"][0]
    assert state["state"] == "Florida"
    assert state["requirement_status"] == "REQUIRED"
    assert state["sufficiency_status"] == "INSUFFICIENT"
    assert state["document_generated"] is False
    assert state["generated_document_text"] is None
    assert "1 more" in state["gap_detail"]
    assert "Admitted Carrier B" in state["gap_detail"]


@_needs_fixtures
async def test_scenario_04_partial_multistate_checklist(es_ctx) -> None:
    """8-state risk: TN/GA confirmed requiring standard diligent search
    (evidence not yet submitted), FL's hedged export-list note routes to
    PENDING_DETERMINATION (not auto-exempt, per FR-7), and the 5 unlisted
    states are explicitly flagged incomplete — never a single collapsed
    verdict."""
    output = await _run(es_ctx, "scenario_04")
    payload = output.payload
    assert payload["overall_status"] == "PARTIAL"
    states = {s["state"]: s for s in payload["state_determinations"]}
    assert len(states) == 8

    assert states["TN"]["requirement_status"] == "REQUIRED"
    assert states["TN"]["sufficiency_status"] == "NOT_APPLICABLE"
    assert states["GA"]["requirement_status"] == "REQUIRED"

    # The core FR-7 judgment call: a hedged, account-specific export-list note
    # must NOT auto-resolve to EXEMPT.
    assert states["FL"]["requirement_status"] == "PENDING_DETERMINATION"
    assert states["FL"]["exemption_basis"] is None

    for code in ("NC", "SC", "VA", "AL", "MS"):
        assert states[code]["requirement_status"] == "PENDING_DETERMINATION"
        assert states[code]["gap_detail"]

    assert all(not s["document_generated"] for s in states.values())


@_needs_fixtures
async def test_run_and_approve(es_ctx_senior, es_session) -> None:
    body = RunRequest(scenario_ref="scenario_01")
    item = await run_diligent_search(body, es_ctx_senior, es_session)
    assert item.status == ReviewStatus.PENDING.value
    approved = await approve(item.id, es_ctx_senior, es_session)
    assert approved.status == ReviewStatus.APPROVED.value


@_needs_fixtures
async def test_escalate_pending_determination(es_ctx_senior, es_session) -> None:
    body = RunRequest(scenario_ref="scenario_04")
    item = await run_diligent_search(body, es_ctx_senior, es_session)
    escalated = await escalate(item.id, es_ctx_senior, es_session)
    assert escalated.status == ReviewStatus.ESCALATED.value


# --- Live path: real MM-07 stub -> broker-entered real per-state data -----
#
# Market Matching's own zero-match fixture (submission_06) genuinely fires
# MM-07 and seeds a real, linked diligent_search review item stub via
# verticals/es/diligent_search_hooks.py — no mocked Gmail needed here, since
# the hook itself is already real regardless of how Market Matching sourced
# the submission (fixture ref or a real live message id).


@_needs_fixtures
async def test_live_submissions_discovers_real_mm07_stub(
    es_ctx, es_session, mock_connectors_mode
) -> None:
    await run_market_matching(
        MarketMatchingRunRequest(submission_ref="submission_06"), es_ctx, es_session
    )
    stubs = await list_live_submissions(es_ctx, es_session)
    assert len(stubs) == 1
    assert stubs[0].submission_id == "submission_06"


@_needs_fixtures
async def test_run_live_mixed_real_per_state_outcomes(
    es_ctx, es_session, mock_connectors_mode
) -> None:
    """Gap-fill: a broker/compliance person enters real per-state facts and
    real declination records for a real MM-07-seeded submission — never
    inferred or invented. DS-01..DS-04's strict, unmodified logic decides
    each state exactly as it does for the fixture path, just fed different
    (real, human-supplied) inputs."""
    await run_market_matching(
        MarketMatchingRunRequest(submission_ref="submission_06"), es_ctx, es_session
    )
    stubs = await list_live_submissions(es_ctx, es_session)
    item_id = stubs[0].item_id

    result = await run_diligent_search_live(
        item_id,
        RunLiveRequest(
            submission_id="submission_06",
            named_insured="Live Test Insured LLC",
            states=[
                LiveStateInput(state="TX", status="exempt", export_list_note="On export list"),
                LiveStateInput(
                    state="CA", status="required", admitted_declinations_required=1,
                    declinations=[
                        LiveDeclinationInput(
                            carrier="Acme Admitted Co", date="2027-01-05", written_evidence=True
                        )
                    ],
                ),
                LiveStateInput(
                    state="NY", status="required", admitted_declinations_required=1,
                    declinations=[
                        LiveDeclinationInput(
                            carrier="Verbal Only Co", date="2027-01-06", written_evidence=False
                        )
                    ],
                ),
                LiveStateInput(state="FL", status="pending"),
            ],
        ),
        es_ctx, es_session,
    )
    payload = result.payload
    assert payload.named_insured == "Live Test Insured LLC"
    states = {s.state: s for s in payload.state_determinations}

    assert states["TX"].requirement_status == "EXEMPT"
    assert states["TX"].exemption_basis == "On export list"

    assert states["CA"].sufficiency_status == "SUFFICIENT"
    assert states["CA"].document_generated is True
    assert states["CA"].generated_document_text

    assert states["NY"].sufficiency_status == "INSUFFICIENT"
    assert states["NY"].document_generated is False
    assert states["NY"].generated_document_text is None

    assert states["FL"].requirement_status == "PENDING_DETERMINATION"

    assert payload.overall_status == "BLOCKED"  # NY's confirmed gap takes priority


@_needs_fixtures
async def test_run_live_missing_required_count_never_defaults_to_zero(
    es_ctx, es_session, mock_connectors_mode
) -> None:
    """Real bug found via live usage (not caught by planning): a "Required"
    state with no declination count entered was being silently treated as
    "0 required" — trivially satisfied by ANY declination, even one. For
    this workflow's own zero-tolerance gate, that's exactly the silent
    false-pass it exists to prevent. Missing count must route through
    DS-01's own null-safety to PENDING_DETERMINATION, never a fabricated
    SUFFICIENT/document_generated."""
    await run_market_matching(
        MarketMatchingRunRequest(submission_ref="submission_06"), es_ctx, es_session
    )
    stubs = await list_live_submissions(es_ctx, es_session)
    item_id = stubs[0].item_id

    result = await run_diligent_search_live(
        item_id,
        RunLiveRequest(
            submission_id="submission_06",
            named_insured="Regression Test Insured LLC",
            states=[
                LiveStateInput(
                    state="CA", status="required", admitted_declinations_required=None,
                    declinations=[
                        LiveDeclinationInput(carrier="Written", date="01/01/2001", written_evidence=True)
                    ],
                ),
            ],
        ),
        es_ctx, es_session,
    )
    ca = result.payload.state_determinations[0]
    assert ca.requirement_status == "PENDING_DETERMINATION"
    assert ca.sufficiency_status == "NOT_APPLICABLE"
    assert ca.document_generated is False
    assert ca.generated_document_text is None


@_needs_fixtures
async def test_run_live_updates_same_item_not_duplicated(
    es_ctx, es_session, mock_connectors_mode
) -> None:
    await run_market_matching(
        MarketMatchingRunRequest(submission_ref="submission_06"), es_ctx, es_session
    )
    stubs = await list_live_submissions(es_ctx, es_session)
    item_id = stubs[0].item_id

    await run_diligent_search_live(
        item_id,
        RunLiveRequest(
            submission_id="submission_06",
            named_insured="Live Test Insured LLC",
            states=[LiveStateInput(state="TX", status="exempt", export_list_note="Exempt")],
        ),
        es_ctx, es_session,
    )

    rows = (
        await es_session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.tenant_id) == es_ctx.tenant_id,
                col(ReviewItemRow.workflow) == "diligent_search",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == item_id

    # A completed item no longer shows up as a pending stub.
    stubs_after = await list_live_submissions(es_ctx, es_session)
    assert stubs_after == []


# ── FR-8 StateRetentionReference tests ───────────────────────────────────────
#
# Test 1: reference entry exists → retention fields populated, citation traced.
# Test 2: no reference entry → null/pending, no regression from pre-change.
# Test 3: multi-state → per-state independent lookup, zero sibling defaulting.
# Test 4: reference absent entirely → all states null, structurally enforced.
# Test 5: full router chain → DB rows → load_all() → payload end-to-end.
#
# Tests 1–3 and 5 use real Workflow_17 fixture scenarios (@_needs_fixtures).
# Test 4 is a pure synchronous unit test on determine_state() — always runs.


@_needs_fixtures
async def test_fr8_retention_populated_when_reference_entry_exists(es_ctx) -> None:
    """Test 1/4 — FR-8: when a StateRetentionReference entry exists for a state,
    the pipeline writes retention_period_years and retention_source into the
    payload, citing the supplied statutory reference exactly.

    Scenario: scenario_01 (Oregon, SUFFICIENT).
    Reference: Oregon → 7 years, "ORS § 742.001(a)".
    """
    pipeline = DiligentSearchPipeline(llm=build_llm_service())
    output = await pipeline.run(
        es_ctx,
        WorkflowInput(source_ref="scenario_01"),
        retention_reference={"Oregon": (7, "ORS § 742.001(a)")},
    )

    state = output.payload["state_determinations"][0]
    assert state["state"] == "Oregon"
    assert state["retention_period_years"] == 7, (
        f"expected 7 from reference entry, got {state['retention_period_years']!r}"
    )
    assert state["retention_source"] == "ORS § 742.001(a)", (
        f"source citation not propagated: {state['retention_source']!r}"
    )


@_needs_fixtures
async def test_fr8_retention_null_when_no_reference_entry_no_regression(es_ctx) -> None:
    """Test 2/4 — FR-8: identical scenario with no reference entry produces
    retention_period_years=null — pre-change behavior preserved exactly.

    This is the "never guess" regression gate: the absence of reference data
    must never trigger a fabricated retention figure or a default.
    """
    pipeline = DiligentSearchPipeline(llm=build_llm_service())
    output = await pipeline.run(
        es_ctx,
        WorkflowInput(source_ref="scenario_01"),
        # Deliberately no retention_reference — mimics "DB has no rows"
    )

    state = output.payload["state_determinations"][0]
    assert state["state"] == "Oregon"
    assert state["retention_period_years"] is None, (
        "no reference entry: retention_period_years must stay null (never guessed), "
        f"got {state['retention_period_years']!r}"
    )
    assert state["retention_source"] is None, (
        "no reference entry: retention_source must stay null, "
        f"got {state['retention_source']!r}"
    )


@_needs_fixtures
async def test_fr8_multistate_per_state_independent_never_inherits_sibling(es_ctx) -> None:
    """Test 3/4 — FR-8 × FR-1/FR-6: multi-state risk uses a fully independent
    lookup per state — a state with no reference entry stays null; it must
    never inherit or default to a sibling state's retention figure.

    Scenario: scenario_04 (8 states: TN, GA, FL, NC, SC, VA, AL, MS).
    Reference supplied for TN (5 yr) and GA (7 yr) only.  All other six states
    must remain null — each is an independent compliance question.
    """
    pipeline = DiligentSearchPipeline(llm=build_llm_service())
    output = await pipeline.run(
        es_ctx,
        WorkflowInput(source_ref="scenario_04"),
        retention_reference={
            "TN": (5, "Tenn. Code Ann. § 56-2-117"),
            "GA": (7, "O.C.G.A. § 33-7-4"),
            # FL, NC, SC, VA, AL, MS deliberately absent from reference
        },
    )

    states = {s["state"]: s for s in output.payload["state_determinations"]}
    assert len(states) == 8, f"scenario_04 should have 8 states, got {list(states)}"

    # TN and GA: populated from the reference entries
    assert states["TN"]["retention_period_years"] == 5
    assert states["TN"]["retention_source"] == "Tenn. Code Ann. § 56-2-117"
    assert states["GA"]["retention_period_years"] == 7
    assert states["GA"]["retention_source"] == "O.C.G.A. § 33-7-4"

    # All six absent states: null — no sibling defaulting, no fallback
    absent_states = ("FL", "NC", "SC", "VA", "AL", "MS")
    for code in absent_states:
        assert states[code]["retention_period_years"] is None, (
            f"FR-1/FR-6 violation: {code} has no reference entry but "
            f"retention_period_years={states[code]['retention_period_years']!r} "
            "(must not inherit from TN/GA or default to any value)"
        )
        assert states[code]["retention_source"] is None, (
            f"FR-1/FR-6 violation: {code} retention_source must be null "
            f"when no reference entry exists, got {states[code]['retention_source']!r}"
        )


def test_fr8_reference_absent_all_null_structurally_enforced() -> None:
    """Test 4/4 — FR-8: when the reference is absent entirely (None, empty
    dict, or a dict with no matching state), determine_state() returns
    retention_period_years=None and retention_source=None for every input —
    the "never guess" invariant is structurally enforced at the engine level,
    not a convention.

    Pure synchronous unit test — no DB, no LLM, no TEST_DATA_ROOT needed.
    Exercises the three forms of "absent reference" the engine can receive.
    """
    # Representative compliant state (SUFFICIENT) — retention should be null
    # regardless of the underlying compliance outcome.
    requirement = {"export_list_class": False, "admitted_declinations_required": 1}
    declinations = [{"carrier": "Acme Admitted Co", "date": "2027-01-01", "written_evidence": True}]

    absent_forms: list[dict | None] = [
        None,                        # router passed nothing (empty DB)
        {},                          # load_all() returned empty dict
        {"OTHER": (3, "Other § 1")}, # non-matching state key
    ]
    for retention_ref in absent_forms:
        det = determine_state("CA", requirement, declinations, retention_reference=retention_ref)
        assert det.retention_period_years is None, (
            f"With retention_reference={retention_ref!r}: "
            f"expected None for CA (no matching entry), "
            f"got {det.retention_period_years!r} — 'never guess' violated"
        )
        assert det.retention_source is None, (
            f"With retention_reference={retention_ref!r}: "
            f"retention_source must be None when no entry, "
            f"got {det.retention_source!r}"
        )

    # Also verify that sufficiency logic is unaffected (no side effects from the lookup)
    det_with_ref = determine_state(
        "CA", requirement, declinations,
        retention_reference={"CA": (7, "CAL. INS. CODE § 1764.2(a)")},
    )
    assert det_with_ref.retention_period_years == 7
    assert det_with_ref.retention_source == "CAL. INS. CODE § 1764.2(a)"
    assert det_with_ref.sufficiency_status == "SUFFICIENT"  # compliance logic unchanged


@_needs_fixtures
async def test_fr8_router_loads_retention_from_db_full_chain(
    es_ctx, es_session
) -> None:
    """Test 5 — FR-8 integration: StateRetentionReference rows in the DB are
    loaded by the router's load_all() call and flow through pipeline.run()
    into the stored OutputPackage payload.

    Proves the complete chain:
      INSERT StateRetentionReference row
      → router calls load_all(session)
      → pipeline.run(retention_reference={...})
      → determine_state() fills retention fields
      → OutputPackageRow.payload contains the figure with correct citation.

    No hardcoded knowledge anywhere in the chain — the figure originates
    solely from the DB row inserted at the start of this test.
    """
    from uuid import uuid4

    # Insert a reference row directly (simulates operator running the loader)
    es_session.add(StateRetentionReferenceRow(
        id=str(uuid4()),
        state="Oregon",
        retention_period_years=7,
        source_citation="ORS § 742.001(a)",
        loaded_from="test_fr8_integration.json",
    ))
    await es_session.commit()

    # Call the router endpoint — it picks up retention_reference from load_all()
    item = await run_diligent_search(
        RunRequest(scenario_ref="scenario_01"), es_ctx, es_session
    )

    # Retrieve the stored output package to inspect the persisted payload
    review = (
        await es_session.execute(
            select(ReviewItemRow).where(col(ReviewItemRow.id) == item.id)
        )
    ).scalar_one()
    pkg = (
        await es_session.execute(
            select(OutputPackageRow).where(
                col(OutputPackageRow.id) == review.output_package_id
            )
        )
    ).scalar_one()

    state = pkg.payload["state_determinations"][0]
    assert state["state"] == "Oregon"
    assert state["retention_period_years"] == 7, (
        f"router did not load retention from DB: got {state['retention_period_years']!r}"
    )
    assert state["retention_source"] == "ORS § 742.001(a)", (
        f"source citation not carried through: {state['retention_source']!r}"
    )
