"""CI batch × G2 profile-store integration tests.

Validates the two CI outcomes end-to-end against synthetic live signals that
exactly match the real Workflow_18 scenario fixture content (Scenario 02 /
Scenario 03 / Scenario 04 payloads reproduced verbatim from the JSON files in
``Data sets/Workflow 9/carrier_intelligence_dataset/``).

TEST_DATA_ROOT is NOT required.  These tests drive the ``run_live()`` path —
the identical entry point the G6 ``carrier_appetite_batch`` monitor uses —
fed from synthetic ``OutputPackageRow`` DB records rather than static fixture
files.  The only component mocked is the LLM (no API key available in CI);
every DB write (profile store, review queue) is exercised against a real
in-memory SQLite session.

The three assertions the task demands:
  1. CONFIRMED_CONSISTENT (Scenario 04 — Coastal Mutual / Habitational,
     4/4 consistent):
       • ``CarrierProfileService.refresh_metadata`` is called exactly once.
       • The new profile row has ``source = CI_METADATA_REFRESH``.
       • ONLY ``appetite_confidence`` and ``appetite_last_updated`` differ from
         the previous version — every substantive field is byte-identical.
       • NO suggestion / ReviewItem is created.

  2. GENUINE_INCONSISTENCY (Scenario 02 — Meridian / Landscaping,
     3 consistent recent declines, 2 explicitly class-level):
       • A ReviewItem with ``status = PENDING_REVIEW`` is created (suggestion
         inbox entry).
       • The payload carries ``evidence`` citing the right submissions and
         ``reason_scope`` values (``class_level`` for SUB-B1/B2,
         ``unstated`` for SUB-B3).
       • NO profile field is auto-changed (``refresh_metadata`` never called).

  3. INSUFFICIENT_SIGNAL / account-specific (Scenario 03 — Ironclad /
     Roofing, 1 inconsistent with "this specific account" reason):
       • Account-specific declines contribute ZERO to class-level evidence
         (``classify_reason_scope`` regression gate).
       • The monitor emits ZERO alerts and creates ZERO ReviewItems.
       • The profile is unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, col, select

import core.models  # noqa: F401 — registers all tables
from core.common.dtos import Ctx, Draft
from core.common.enums import ReviewStatus, Role, Vertical
from core.models import CarrierAppetiteProfile as ProfileRow
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.models import Tenant
from verticals.es.carrier_profile_store import (
    SOURCE_CI,
    SOURCE_SEED,
    CarrierProfileService,
    MetadataRefreshDTO,
)
from verticals.es.decision_core.carrier_profiles import (
    CarrierProfile,
    PremiumBand,
    SeverityCeiling,
    SubmissionRequirements,
)
from verticals.es.workflows.carrier_appetite_intelligence.consistency_engine import (
    classify_reason_scope,
    score_pattern,
)
from verticals.es.workflows.carrier_appetite_intelligence.service import (
    CarrierAppetiteIntelligencePipeline,
)

# ── Shared as_of date — same convention as test_es_monitors.py ────────────────

AS_OF = date(2027, 7, 1)

# ── Fixture data reproduced verbatim from the Workflow_18 JSON files ──────────
#
# Carrier names map directly to carrier_id when the JSON panel (Workflow_10)
# is unavailable (TEST_DATA_ROOT not set).  The profile store is seeded with
# carrier_id == carrier_name so refresh_metadata can find the row.

# Scenario 04 — Coastal Mutual Specialty / habitational  (CONFIRMED_CONSISTENT)
_COASTAL_NAME = "Coastal Mutual Specialty"
_COASTAL_SIGNALS: list[dict[str, Any]] = [
    {"sub": "SUB-D1", "reason": None, "consistent": True, "date": "2027-04-01"},
    {"sub": "SUB-D2", "reason": None, "consistent": True, "date": "2027-05-15"},
    {"sub": "SUB-D3", "reason": None, "consistent": True, "date": "2027-06-20"},
    {"sub": "SUB-D4", "reason": None, "consistent": True, "date": "2027-07-25"},
]

# Scenario 02 — Meridian Excess & Surplus / landscaping  (GENUINE_INCONSISTENCY)
_MERIDIAN_NAME = "Meridian Excess & Surplus"
_MERIDIAN_SIGNALS: list[dict[str, Any]] = [
    {"sub": "SUB-B4", "reason": None, "consistent": True, "date": "2027-04-01"},
    {"sub": "SUB-B1", "reason": "class no longer written", "consistent": False, "date": "2027-06-10"},
    {"sub": "SUB-B2", "reason": "class no longer written", "consistent": False, "date": "2027-06-25"},
    {"sub": "SUB-B3", "reason": "no reason given", "consistent": False, "date": "2027-07-15"},
]

# Scenario 03 — Ironclad Casualty Solutions / roofing  (INSUFFICIENT_SIGNAL)
_IRONCLAD_NAME = "Ironclad Casualty Solutions"
_IRONCLAD_SIGNALS: list[dict[str, Any]] = [
    {"sub": "SUB-C1", "reason": None, "consistent": True, "date": "2027-05-01"},
    {"sub": "SUB-C2", "reason": "severity exceeded ceiling for this specific account", "consistent": False, "date": "2027-06-01"},
    {"sub": "SUB-C3", "reason": None, "consistent": True, "date": "2027-07-01"},
]


# ── Session / ctx fixtures ────────────────────────────────────────────────────


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        t = Tenant(id="ci-test", name="CI Tests", vertical=Vertical.ES, domain="ci.test")
        s.add(t)
        await s.commit()
        yield s
    await engine.dispose()


@pytest.fixture
def ctx() -> Ctx:
    return Ctx(tenant_id="ci-test", vertical=Vertical.ES, user_id="ci-bot", role=Role.ADMIN)


# ── LLM stub ─────────────────────────────────────────────────────────────────


def _stub_llm() -> Any:
    """Stub LLM that returns pre-cooked drafts without touching any API."""
    mock = MagicMock()
    mock.draft = AsyncMock(return_value=Draft(text="[CI stub draft]", citations=[]))
    return mock


# ── Signal-seeding helpers ─────────────────────────────────────────────────────


def _make_qc_row(
    tenant_id: str,
    carrier_name: str,
    signals: list[dict[str, Any]],
) -> OutputPackageRow:
    """Build a single ``quote_comparison`` OutputPackageRow whose quotes
    reproduce the exact signal_log outcomes from the Workflow_18 fixture.

    Consistent signals map to DECLINATION + ``declination_appetite_consistency
    = 'consistent'`` (the carrier declined but in line with stated appetite).
    Inconsistent signals map to DECLINATION + ``'inconsistent'``.
    Both are included by ``_classifiable_declinations``; only
    ``declination_appetite_consistency = 'unable_to_determine'`` is excluded.
    """
    quotes = []
    for sig in signals:
        consistency = "consistent" if sig["consistent"] else "inconsistent"
        quotes.append(
            {
                "quote_id": f"q-{sig['sub']}",
                "submission_id": sig["sub"],
                "carrier_name": carrier_name,
                "response_type": "DECLINATION",
                "declination_reason": sig["reason"],
                "declination_appetite_consistency": consistency,
            }
        )
    return OutputPackageRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        submission_id=f"live-{carrier_name}",
        workflow="quote_comparison",
        payload={"submission_id": f"live-{carrier_name}", "quotes": quotes},
    )


def _seed_profile(
    tenant_id: str,
    carrier_name: str,
    *,
    carrier_id: str | None = None,
    appetite_confidence: str = "high",
) -> CarrierProfile:
    """Return a CarrierProfile for seeding.  ``carrier_id`` defaults to
    ``carrier_name`` — this is correct when the JSON panel is unavailable
    (TEST_DATA_ROOT not set), because ``build_live_signal_log`` falls back
    to using carrier_name as the id."""
    cid = carrier_id or carrier_name
    return CarrierProfile(
        carrier_id=cid,
        carrier_name=carrier_name,
        class_codes_accepted=("habitational", "landscaping", "roofing_contractor"),
        class_codes_excluded=("frame_construction",),
        states_licensed=("TX", "FL", "CA"),
        premium_band=PremiumBand(min=50_000.0, max=5_000_000.0),
        submission_requirements=SubmissionRequirements(
            min_loss_run_years=3,
            required_documents=("ACORD 125", "loss_run_3yr"),
            acceptance_window_days=90,
        ),
        severity_ceiling=SeverityCeiling(max_single_claim_incurred=1_000_000.0),
        appetite_confidence=appetite_confidence,
        historical_hit_rate_this_class=0.72,
        lines_written=("GL", "Excess"),
        notes="Seeded for CI batch integration tests.",
    )


# ── Helpers to query DB state ─────────────────────────────────────────────────


async def _review_items(session: AsyncSession, tenant_id: str, workflow: str) -> list[ReviewItemRow]:
    rows = (
        await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.tenant_id) == tenant_id,
                col(ReviewItemRow.workflow) == workflow,
            )
        )
    ).scalars().all()
    return list(rows)


async def _profile_versions(
    session: AsyncSession, tenant_id: str, carrier_id: str
) -> list[ProfileRow]:
    rows = (
        await session.execute(
            select(ProfileRow).where(
                col(ProfileRow.tenant_id) == tenant_id,
                col(ProfileRow.carrier_id) == carrier_id,
            )
        )
    ).scalars().all()
    return list(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONFIRMED_CONSISTENT — Scenario 04 (Coastal Mutual / Habitational)
# ═══════════════════════════════════════════════════════════════════════════════


async def test_confirmed_consistent_pipeline_output(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Baseline: the pipeline recognises 4/4 consistent outcomes as
    CONFIRMED_CONSISTENT and populates metadata_refresh with exactly two keys."""
    qc_row = _make_qc_row(ctx.tenant_id, _COASTAL_NAME, _COASTAL_SIGNALS)
    session.add(qc_row)
    await session.commit()

    pipeline = CarrierAppetiteIntelligencePipeline(llm=_stub_llm())
    output = await pipeline.run_live(ctx, session, _COASTAL_NAME)

    payload = output.payload
    assert payload["pattern_type"] == "CONFIRMED_CONSISTENT"
    assert payload["status"] == "METADATA_AUTO_UPDATED"
    assert payload["suggested_action"] is None
    assert payload["metadata_refresh"] is not None

    # FR-4 gate: metadata_refresh carries ONLY the two allowed keys.
    refresh_keys = set(payload["metadata_refresh"].keys())
    assert refresh_keys == {"appetite_confidence", "appetite_last_updated"}, (
        f"metadata_refresh must have exactly 2 keys, found: {refresh_keys}"
    )


async def test_confirmed_consistent_batch_writes_profile_version(
    session: AsyncSession, ctx: Ctx
) -> None:
    """End-to-end G2 write: after the batch detects CONFIRMED_CONSISTENT,
    CarrierProfileService.refresh_metadata is called → new profile version
    with source=CI_METADATA_REFRESH where ONLY the two CI fields changed.

    NO suggestion / ReviewItem is created (CI-04 must not fire here).
    """
    # Seed QC signals.
    qc_row = _make_qc_row(ctx.tenant_id, _COASTAL_NAME, _COASTAL_SIGNALS)
    session.add(qc_row)
    await session.commit()

    # Seed the carrier profile (carrier_id = carrier_name since no JSON panel).
    profiles = [_seed_profile(ctx.tenant_id, _COASTAL_NAME, appetite_confidence="high")]
    await CarrierProfileService.seed_from_json(session, ctx.tenant_id, profiles)
    v1 = await CarrierProfileService.get_latest(session, ctx.tenant_id, _COASTAL_NAME)
    assert v1 is not None, "pre-condition: profile must exist before batch run"
    assert v1.source == SOURCE_SEED

    # Capture all v1 substantive fields for the byte-identical assertion below.
    v1_class_codes_accepted = list(v1.class_codes_accepted)
    v1_class_codes_excluded = list(v1.class_codes_excluded)
    v1_states_licensed = list(v1.states_licensed)
    v1_premium_band = dict(v1.premium_band or {})
    v1_severity_ceiling = dict(v1.severity_ceiling or {})
    v1_submission_requirements = dict(v1.submission_requirements or {})
    v1_historical_hit_rate = v1.historical_hit_rate_this_class
    v1_lines_written = list(v1.lines_written)
    v1_notes = v1.notes
    v1_gap_policy = dict(v1.gap_policy or {})

    # Run the pipeline (same call the batch monitor makes).
    pipeline = CarrierAppetiteIntelligencePipeline(llm=_stub_llm())
    output = await pipeline.run_live(ctx, session, _COASTAL_NAME)
    payload = output.payload
    assert payload["pattern_type"] == "CONFIRMED_CONSISTENT"

    # Apply the metadata refresh exactly as the monitor does.
    mr_payload = payload.get("metadata_refresh") or {}
    dto = MetadataRefreshDTO(
        appetite_confidence=mr_payload["appetite_confidence"],
        appetite_last_updated=mr_payload["appetite_last_updated"],
    )
    v2 = await CarrierProfileService.refresh_metadata(session, ctx, _COASTAL_NAME, dto)

    # ── Assertion 1: New version created with CI source. ──────────────────────
    assert v2.version_id != v1.version_id
    assert v2.source == SOURCE_CI
    assert v2.supersedes_version_id == v1.version_id

    # ── Assertion 2: ONLY the two CI fields changed. ──────────────────────────
    assert v2.appetite_confidence == mr_payload["appetite_confidence"]
    assert v2.appetite_last_updated == mr_payload["appetite_last_updated"]

    # ── Assertion 3: Every substantive field is byte-identical to v1. ─────────
    assert list(v2.class_codes_accepted) == v1_class_codes_accepted, "class_codes_accepted must not change"
    assert list(v2.class_codes_excluded) == v1_class_codes_excluded, "class_codes_excluded must not change"
    assert list(v2.states_licensed) == v1_states_licensed, "states_licensed must not change"
    assert dict(v2.premium_band or {}) == v1_premium_band, "premium_band must not change"
    assert dict(v2.severity_ceiling or {}) == v1_severity_ceiling, "severity_ceiling must not change"
    assert dict(v2.submission_requirements or {}) == v1_submission_requirements, "submission_requirements must not change"
    assert v2.historical_hit_rate_this_class == v1_historical_hit_rate, "hit_rate must not change"
    assert list(v2.lines_written) == v1_lines_written, "lines_written must not change"
    assert v2.notes == v1_notes, "notes must not change"
    assert dict(v2.gap_policy or {}) == v1_gap_policy, "gap_policy must not change"

    # ── Assertion 4: No suggestion created. ──────────────────────────────────
    items = await _review_items(session, ctx.tenant_id, "carrier_appetite_intelligence")
    assert len(items) == 0, (
        "CONFIRMED_CONSISTENT must NOT create a ReviewItem suggestion — "
        f"found {len(items)}"
    )


async def test_confirmed_consistent_monitor_emits_ci_metadata_refreshed_alert(
    session: AsyncSession, ctx: Ctx
) -> None:
    """The full G6 batch monitor dispatches CI_METADATA_REFRESHED (INFO)
    and calls refresh_metadata exactly once for a CONFIRMED_CONSISTENT carrier."""
    from core.jobs.monitor import get_monitors

    import verticals.es.monitors  # noqa: F401 — registers all monitors

    qc_row = _make_qc_row(ctx.tenant_id, _COASTAL_NAME, _COASTAL_SIGNALS)
    session.add(qc_row)
    await session.commit()

    # Seed profile so refresh_metadata can find a base row.
    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id,
        [_seed_profile(ctx.tenant_id, _COASTAL_NAME, appetite_confidence="high")],
    )

    with patch(
        "verticals.es.monitors.carrier_appetite_batch.build_llm_service",
        return_value=_stub_llm(),
    ):
        monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
        alerts = await monitor.run(session, ctx, AS_OF)

    # Exactly one alert: CI_METADATA_REFRESHED (INFO).
    assert len(alerts) == 1, f"Expected 1 alert, got {len(alerts)}: {[a.alert_type for a in alerts]}"
    alert = alerts[0]
    assert alert.alert_type == "CI_METADATA_REFRESHED"
    assert alert.severity == "INFO"
    assert alert.entity_ref == _COASTAL_NAME  # carrier_id = name when no panel
    assert alert.payload["appetite_confidence"]  # must be populated (non-empty)
    assert alert.payload["appetite_last_updated"]  # must be populated

    # Profile has a new CI version.
    v_current, history = await CarrierProfileService.get_with_history(
        session, ctx.tenant_id, _COASTAL_NAME
    )
    assert v_current is not None
    assert v_current.source == SOURCE_CI
    assert len(history) == 1 and history[0].source == SOURCE_SEED

    # No suggestion.
    items = await _review_items(session, ctx.tenant_id, "carrier_appetite_intelligence")
    assert len(items) == 0


async def test_confirmed_consistent_idempotent_skip_already_refreshed_today(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Running the batch twice on the same day must NOT create a second CI
    version (idempotency guard: _already_refreshed_today skips the carrier).

    Uses date.today() as as_of so the profile's created_at (real-time) is
    compared against the same date the guard queries — the only way to make
    this check pass without mocking datetime in SQLite.
    """
    from datetime import date as _date

    from core.jobs.monitor import get_monitors

    import verticals.es.monitors  # noqa: F401

    today = _date.today()  # must match what SQLite stores as created_at.date()

    qc_row = _make_qc_row(ctx.tenant_id, _COASTAL_NAME, _COASTAL_SIGNALS)
    session.add(qc_row)
    await session.commit()
    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id,
        [_seed_profile(ctx.tenant_id, _COASTAL_NAME)],
    )

    with patch(
        "verticals.es.monitors.carrier_appetite_batch.build_llm_service",
        return_value=_stub_llm(),
    ):
        monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
        alerts_run1 = await monitor.run(session, ctx, today)
        alerts_run2 = await monitor.run(session, ctx, today)

    # First run: 1 alert. Second run: 0 (skipped — already refreshed today).
    assert len(alerts_run1) == 1
    assert len(alerts_run2) == 0, (
        f"Second run must be a no-op — idempotency guard did not fire. "
        f"Got {len(alerts_run2)} alert(s): {[a.alert_type for a in alerts_run2]}"
    )

    # Still only 2 versions total: SEED + one CI (not two CI).
    _curr, history = await CarrierProfileService.get_with_history(
        session, ctx.tenant_id, _COASTAL_NAME
    )
    assert len(history) == 1, f"Expected SEED + 1 CI version, found {len(history) + 1} total"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GENUINE_INCONSISTENCY — Scenario 02 (Meridian / Landscaping)
# ═══════════════════════════════════════════════════════════════════════════════


async def test_genuine_inconsistency_pipeline_output(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Baseline: the pipeline recognises 3 inconsistent (2 class-level, 1
    unstated) as GENUINE_INCONSISTENCY and surfaces evidence with correct
    reason_scopes — exactly matching Scenario 02's fixture."""
    qc_row = _make_qc_row(ctx.tenant_id, _MERIDIAN_NAME, _MERIDIAN_SIGNALS)
    session.add(qc_row)
    await session.commit()

    pipeline = CarrierAppetiteIntelligencePipeline(llm=_stub_llm())
    output = await pipeline.run_live(ctx, session, _MERIDIAN_NAME)

    payload = output.payload
    assert payload["pattern_type"] == "GENUINE_INCONSISTENCY"
    assert payload["status"] == "PENDING_REVIEW"
    assert payload["metadata_refresh"] is None

    # Evidence must cite the three inconsistent submissions with correct scopes.
    reasons = {e["submission_id"]: e["reason_scope"] for e in payload["evidence"]}
    assert reasons.get("SUB-B1") == "class_level", f"SUB-B1 should be class_level, got {reasons.get('SUB-B1')}"
    assert reasons.get("SUB-B2") == "class_level", f"SUB-B2 should be class_level, got {reasons.get('SUB-B2')}"
    assert reasons.get("SUB-B3") == "unstated", f"SUB-B3 should be unstated, got {reasons.get('SUB-B3')}"

    # Consistent outcome is in evidence but has reason_scope=None (not classified).
    b4_entry = next((e for e in payload["evidence"] if e["submission_id"] == "SUB-B4"), None)
    assert b4_entry is not None
    assert b4_entry["reason_scope"] is None  # consistent — no reason scope assigned


async def test_genuine_inconsistency_batch_creates_suggestion_no_profile_change(
    session: AsyncSession, ctx: Ctx
) -> None:
    """End-to-end G2 write: after the batch detects GENUINE_INCONSISTENCY,
    a ReviewItem with PENDING_REVIEW is created in the inbox.

    NO profile field is auto-changed — refresh_metadata must NOT be called.
    NO new profile version is written — verify by checking version count.
    """
    qc_row = _make_qc_row(ctx.tenant_id, _MERIDIAN_NAME, _MERIDIAN_SIGNALS)
    session.add(qc_row)
    await session.commit()

    # Seed the carrier profile.
    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id,
        [_seed_profile(ctx.tenant_id, _MERIDIAN_NAME, appetite_confidence="high")],
    )
    v1 = await CarrierProfileService.get_latest(session, ctx.tenant_id, _MERIDIAN_NAME)
    assert v1 is not None

    # Run pipeline (same as monitor) and enqueue via review queue.
    from core.review_queue import DefaultReviewQueueService
    from verticals.es.workflows.carrier_appetite_intelligence.service import WORKFLOW_NAME

    pipeline = CarrierAppetiteIntelligencePipeline(llm=_stub_llm())
    output = await pipeline.run_live(ctx, session, _MERIDIAN_NAME)
    assert output.payload["pattern_type"] == "GENUINE_INCONSISTENCY"

    # Enqueue — exactly what the monitor's CI-04 branch does.
    await DefaultReviewQueueService().enqueue(session, ctx, output, WORKFLOW_NAME)

    # ── Assertion 1: ReviewItem created with PENDING_REVIEW. ──────────────────
    items = await _review_items(session, ctx.tenant_id, WORKFLOW_NAME)
    assert len(items) == 1, f"Expected 1 ReviewItem, got {len(items)}"
    item = items[0]
    assert item.status == ReviewStatus.PENDING

    # ── Assertion 2: OutputPackage payload carries full evidence with scopes. ─
    assert item.output_package_id is not None
    pkg = (
        await session.execute(
            select(OutputPackageRow).where(
                col(OutputPackageRow.id) == item.output_package_id
            )
        )
    ).scalar_one_or_none()
    assert pkg is not None and pkg.payload is not None

    evidence = pkg.payload.get("evidence", [])
    assert len(evidence) == 4, f"All 4 observed outcomes must appear in evidence, got {len(evidence)}"

    by_sub = {e["submission_id"]: e for e in evidence}
    assert by_sub["SUB-B1"]["reason_scope"] == "class_level"
    assert by_sub["SUB-B2"]["reason_scope"] == "class_level"
    assert by_sub["SUB-B3"]["reason_scope"] == "unstated"
    assert by_sub["SUB-B4"]["reason_scope"] is None  # consistent, no scope

    # suggested_action is populated (LLM drafted a recommendation).
    assert pkg.payload.get("suggested_action")

    # ── Assertion 3: NO profile field auto-changed. ───────────────────────────
    versions = await _profile_versions(session, ctx.tenant_id, _MERIDIAN_NAME)
    assert len(versions) == 1, (
        "GENUINE_INCONSISTENCY must NOT write a new profile version — "
        f"found {len(versions)} versions"
    )
    sole_version = versions[0]
    assert sole_version.source == SOURCE_SEED
    assert sole_version.version_id == v1.version_id


async def test_genuine_inconsistency_monitor_emits_ci_suggestion_created_alert(
    session: AsyncSession, ctx: Ctx
) -> None:
    """The full G6 batch monitor dispatches CI_SUGGESTION_CREATED (WARN)
    and creates exactly one PENDING_REVIEW ReviewItem for GENUINE_INCONSISTENCY."""
    from core.jobs.monitor import get_monitors

    import verticals.es.monitors  # noqa: F401

    qc_row = _make_qc_row(ctx.tenant_id, _MERIDIAN_NAME, _MERIDIAN_SIGNALS)
    session.add(qc_row)
    await session.commit()

    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id,
        [_seed_profile(ctx.tenant_id, _MERIDIAN_NAME, appetite_confidence="high")],
    )

    with patch(
        "verticals.es.monitors.carrier_appetite_batch.build_llm_service",
        return_value=_stub_llm(),
    ):
        monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
        alerts = await monitor.run(session, ctx, AS_OF)

    # Exactly one alert: CI_SUGGESTION_CREATED (WARN).
    assert len(alerts) == 1, f"Expected 1 alert, got {len(alerts)}"
    alert = alerts[0]
    assert alert.alert_type == "CI_SUGGESTION_CREATED"
    assert alert.severity == "WARN"
    assert alert.entity_ref == _MERIDIAN_NAME

    # Alert payload shows 2 class-level inconsistent declines.
    assert alert.payload["class_level_inconsistent_count"] == 2, (
        "Only SUB-B1 and SUB-B2 carry class-level reasons; "
        f"got count={alert.payload['class_level_inconsistent_count']}"
    )
    assert alert.payload["suggestion_id"]  # UUID populated

    # ReviewItem in inbox.
    items = await _review_items(session, ctx.tenant_id, "carrier_appetite_intelligence")
    assert len(items) == 1
    assert items[0].status == ReviewStatus.PENDING

    # Profile NOT modified.
    versions = await _profile_versions(session, ctx.tenant_id, _MERIDIAN_NAME)
    assert len(versions) == 1
    assert versions[0].source == SOURCE_SEED


async def test_genuine_inconsistency_idempotent_no_duplicate_suggestion(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Running the batch twice must NOT create a duplicate suggestion.
    The second run detects a PENDING suggestion already exists and skips."""
    from core.jobs.monitor import get_monitors

    import verticals.es.monitors  # noqa: F401

    qc_row = _make_qc_row(ctx.tenant_id, _MERIDIAN_NAME, _MERIDIAN_SIGNALS)
    session.add(qc_row)
    await session.commit()

    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id,
        [_seed_profile(ctx.tenant_id, _MERIDIAN_NAME)],
    )

    with patch(
        "verticals.es.monitors.carrier_appetite_batch.build_llm_service",
        return_value=_stub_llm(),
    ):
        monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
        alerts_run1 = await monitor.run(session, ctx, AS_OF)
        alerts_run2 = await monitor.run(session, ctx, AS_OF)

    assert len(alerts_run1) == 1
    assert len(alerts_run2) == 0  # second run skips: pending suggestion exists

    items = await _review_items(session, ctx.tenant_id, "carrier_appetite_intelligence")
    assert len(items) == 1  # exactly one, not two


# ═══════════════════════════════════════════════════════════════════════════════
# 3. INSUFFICIENT_SIGNAL / account-specific — Scenario 03 (Ironclad / Roofing)
# ═══════════════════════════════════════════════════════════════════════════════


def test_account_specific_reason_scope_classification() -> None:
    """CI-02 regression gate: 'severity exceeded ceiling for this specific
    account' must be classified as account_specific — never class_level.

    This is the pure consistency_engine test (no DB, no pipeline) that
    proves the zero-contribution property at the type-system level."""
    reason = "severity exceeded ceiling for this specific account"
    scope = classify_reason_scope(reason)
    assert scope == "account_specific", (
        f"Expected 'account_specific', got '{scope}'. "
        "Account-specific decline reasons must NEVER be scored as class-level evidence."
    )

    # Contrast: genuine class-level reasons are correctly classified.
    assert classify_reason_scope("class no longer written") == "class_level"
    assert classify_reason_scope("appetite has changed for this class") == "class_level"

    # Unstated / no reason.
    assert classify_reason_scope(None) == "unstated"
    assert classify_reason_scope("no reason given") == "unstated"


def test_account_specific_score_pattern_produces_insufficient_signal() -> None:
    """Scenario 03 exact fixture: 3 outcomes, 1 inconsistent with account-
    specific reason.  score_pattern must return INSUFFICIENT_SIGNAL with
    class_level_inconsistent_count == 0 (not 1)."""
    outcomes = [
        {"submission_id": "SUB-C1", "outcome": "quoted", "date": "2027-05-01", "consistent_with_profile": True},
        {
            "submission_id": "SUB-C2",
            "outcome": "declined",
            "date": "2027-06-01",
            "consistent_with_profile": False,
            "reason_given": "severity exceeded ceiling for this specific account",
        },
        {"submission_id": "SUB-C3", "outcome": "quoted", "date": "2027-07-01", "consistent_with_profile": True},
    ]
    result = score_pattern(outcomes)
    assert result.pattern_type == "INSUFFICIENT_SIGNAL"
    assert result.class_level_inconsistent_count == 0, (
        "Account-specific declines must contribute ZERO to class-level evidence."
    )

    # Verify the account_specific submission is present in evidence with correct scope.
    by_sub = {e.submission_id: e for e in result.evidence}
    assert by_sub["SUB-C2"].reason_scope == "account_specific"


async def test_insufficient_signal_pipeline_output(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Baseline: the pipeline recognises the Scenario 03 pattern as
    INSUFFICIENT_SIGNAL with the account-specific reason correctly classified."""
    qc_row = _make_qc_row(ctx.tenant_id, _IRONCLAD_NAME, _IRONCLAD_SIGNALS)
    session.add(qc_row)
    await session.commit()

    pipeline = CarrierAppetiteIntelligencePipeline(llm=_stub_llm())
    output = await pipeline.run_live(ctx, session, _IRONCLAD_NAME)

    payload = output.payload
    assert payload["pattern_type"] == "INSUFFICIENT_SIGNAL"
    assert payload["status"] == "SUPPRESSED"
    assert payload["suggested_action"] is None
    assert payload["metadata_refresh"] is None

    # The account-specific submission is in evidence with correct scope.
    by_sub = {e["submission_id"]: e for e in payload["evidence"]}
    assert by_sub["SUB-C2"]["reason_scope"] == "account_specific", (
        "Account-specific declines must appear in evidence labelled as such, "
        "not silently excluded or relabelled."
    )


async def test_insufficient_signal_batch_emits_zero_alerts_zero_db_writes(
    session: AsyncSession, ctx: Ctx
) -> None:
    """The full G6 batch monitor produces NO alerts and NO ReviewItems for
    INSUFFICIENT_SIGNAL.  The profile is completely unchanged."""
    from core.jobs.monitor import get_monitors

    import verticals.es.monitors  # noqa: F401

    qc_row = _make_qc_row(ctx.tenant_id, _IRONCLAD_NAME, _IRONCLAD_SIGNALS)
    session.add(qc_row)
    await session.commit()

    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id,
        [_seed_profile(ctx.tenant_id, _IRONCLAD_NAME, appetite_confidence="medium")],
    )
    v1 = await CarrierProfileService.get_latest(session, ctx.tenant_id, _IRONCLAD_NAME)
    assert v1 is not None

    with patch(
        "verticals.es.monitors.carrier_appetite_batch.build_llm_service",
        return_value=_stub_llm(),
    ):
        monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
        alerts = await monitor.run(session, ctx, AS_OF)

    # No alerts.
    assert alerts == [], f"Expected 0 alerts for INSUFFICIENT_SIGNAL, got: {[a.alert_type for a in alerts]}"

    # No ReviewItems.
    items = await _review_items(session, ctx.tenant_id, "carrier_appetite_intelligence")
    assert items == [], f"Expected 0 review items, got {len(items)}"

    # Profile unchanged: still exactly 1 version (the SEED row).
    versions = await _profile_versions(session, ctx.tenant_id, _IRONCLAD_NAME)
    assert len(versions) == 1
    assert versions[0].version_id == v1.version_id
    assert versions[0].source == SOURCE_SEED


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Cross-scenario: multi-carrier batch run
# ═══════════════════════════════════════════════════════════════════════════════


async def test_multi_carrier_batch_dispatches_independently(
    session: AsyncSession, ctx: Ctx
) -> None:
    """A single batch run across three carriers (one per scenario) routes each
    to the correct path independently — proving the G6 dispatch loop never
    cross-contaminates carrier state."""
    from core.jobs.monitor import get_monitors

    import verticals.es.monitors  # noqa: F401

    # Seed all three carriers' signals.
    session.add(_make_qc_row(ctx.tenant_id, _COASTAL_NAME, _COASTAL_SIGNALS))   # → CONFIRMED_CONSISTENT
    session.add(_make_qc_row(ctx.tenant_id, _MERIDIAN_NAME, _MERIDIAN_SIGNALS))  # → GENUINE_INCONSISTENCY
    session.add(_make_qc_row(ctx.tenant_id, _IRONCLAD_NAME, _IRONCLAD_SIGNALS))  # → INSUFFICIENT_SIGNAL
    await session.commit()

    # Seed profiles for all three.
    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id,
        [
            _seed_profile(ctx.tenant_id, _COASTAL_NAME, appetite_confidence="high"),
            _seed_profile(ctx.tenant_id, _MERIDIAN_NAME, appetite_confidence="high"),
            _seed_profile(ctx.tenant_id, _IRONCLAD_NAME, appetite_confidence="medium"),
        ],
    )

    with patch(
        "verticals.es.monitors.carrier_appetite_batch.build_llm_service",
        return_value=_stub_llm(),
    ):
        monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
        alerts = await monitor.run(session, ctx, AS_OF)

    # Exactly 2 alerts total: CI_METADATA_REFRESHED for Coastal,
    # CI_SUGGESTION_CREATED for Meridian.  Ironclad is suppressed → 0.
    alert_types = {a.alert_type for a in alerts}
    assert "CI_METADATA_REFRESHED" in alert_types, f"Missing CI_METADATA_REFRESHED in {alert_types}"
    assert "CI_SUGGESTION_CREATED" in alert_types, f"Missing CI_SUGGESTION_CREATED in {alert_types}"
    assert len(alerts) == 2, f"Expected exactly 2 alerts, got {len(alerts)}: {[a.alert_type for a in alerts]}"

    # Coastal: has a CI version.
    coastal_v, _ = await CarrierProfileService.get_with_history(session, ctx.tenant_id, _COASTAL_NAME)
    assert coastal_v is not None and coastal_v.source == SOURCE_CI

    # Meridian: still 1 version (SEED), has a ReviewItem.
    meridian_v, _ = await CarrierProfileService.get_with_history(session, ctx.tenant_id, _MERIDIAN_NAME)
    assert meridian_v is not None and meridian_v.source == SOURCE_SEED
    meridian_items = await _review_items(session, ctx.tenant_id, "carrier_appetite_intelligence")
    assert len(meridian_items) == 1

    # Ironclad: still 1 version (SEED), no ReviewItem.
    ironclad_v, _ = await CarrierProfileService.get_with_history(session, ctx.tenant_id, _IRONCLAD_NAME)
    assert ironclad_v is not None and ironclad_v.source == SOURCE_SEED
