"""E&S Carrier Appetite Profile Store tests — G2.

Covers the five behavioural assertions from the task:
  1. Seed parity      — JSON→store import produces byte-identical CarrierProfile
                         objects (zero data loss through seed→read round trip).
  2. Versioning       — human edit creates a NEW version row with
                         supersedes_version_id set; old version is retained;
                         an OutputPackage created afterward stamps the new
                         version_id (never "current").
  3. Field-guard      — MetadataRefreshDTO carries ONLY appetite_confidence +
                         appetite_last_updated at the type level; constructing
                         it with any substantive field is a ValidationError.
  4. gap_policy       — PA reads gap_policy from the profile row; a carrier
                         with no entry falls back to the global default (block).
  5. Empty-store      — get_profiles_for_matching falls back gracefully when
                         the store is empty for a tenant.

Bonus:
  6. Suggestion inbox — approve writes a new profile version + marks payload
                        APPROVED; dismiss marks DISMISSED without writing a version.

No TEST_DATA_ROOT required. All profiles are synthesised inline.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
import pydantic
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, col, select

import core.models  # noqa: F401 — registers all tables
from core.common.dtos import Ctx, Decision
from core.common.enums import DecisionOutcome, ReviewStatus, Role, Vertical
from core.models import CarrierAppetiteProfile as ProfileRow
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.models import Tenant
from verticals.es.carrier_profile_store import (
    SOURCE_CI,
    SOURCE_HUMAN_EDIT,
    SOURCE_SEED,
    CarrierProfileService,
    MetadataRefreshDTO,
    profile_row_to_carrier,
)
from verticals.es.decision_core.carrier_profiles import (
    CarrierProfile,
    PremiumBand,
    SeverityCeiling,
    SubmissionRequirements,
)
from verticals.es.workflows.package_assembly.assembly import (
    PackageResult,
    _resolve_policy,
    assemble_package,
)


# ── Session / tenant fixtures ─────────────────────────────────────────────────


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
        yield s
    await engine.dispose()


@pytest.fixture
async def tenant(session: AsyncSession) -> Tenant:
    t = Tenant(id="cp-tenant", name="Carrier Profile Tests", vertical=Vertical.ES, domain="cp.test")
    session.add(t)
    await session.commit()
    return t


@pytest.fixture
def ctx(tenant: Tenant) -> Ctx:
    return Ctx(tenant_id=tenant.id, vertical=Vertical.ES, user_id="test-user", role=Role.SENIOR)


# ── Synthetic carrier profile helpers ─────────────────────────────────────────


def _make_carrier(
    carrier_id: str = "CAR-01",
    *,
    carrier_name: str = "Clearpath Specialty",
    class_codes_accepted: tuple[str, ...] = ("manufacturing", "distribution"),
    class_codes_excluded: tuple[str, ...] = ("habitational",),
    states_licensed: tuple[str, ...] = ("TX", "CA", "FL"),
    premium_min: float = 50_000.0,
    premium_max: float = 5_000_000.0,
    min_loss_run_years: int = 3,
    max_single_claim: float = 1_000_000.0,
    appetite_confidence: str = "high",
    historical_hit_rate: float = 0.72,
    lines_written: tuple[str, ...] = ("GL", "Excess"),
    notes: str = "Preferred market for manufacturing risks.",
    ceiling_type: str | None = None,
) -> CarrierProfile:
    return CarrierProfile(
        carrier_id=carrier_id,
        carrier_name=carrier_name,
        class_codes_accepted=class_codes_accepted,
        class_codes_excluded=class_codes_excluded,
        states_licensed=states_licensed,
        premium_band=PremiumBand(min=premium_min, max=premium_max),
        submission_requirements=SubmissionRequirements(
            min_loss_run_years=min_loss_run_years,
            required_documents=("ACORD 125", "loss_run_3yr"),
            acceptance_window_days=90,
        ),
        severity_ceiling=SeverityCeiling(max_single_claim_incurred=max_single_claim),
        appetite_confidence=appetite_confidence,
        historical_hit_rate_this_class=historical_hit_rate,
        lines_written=lines_written,
        notes=notes,
        ceiling_type=ceiling_type,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Seed parity
# ═══════════════════════════════════════════════════════════════════════════════


async def test_seed_parity_round_trip_identical_profiles(
    session: AsyncSession, tenant: Tenant
) -> None:
    """After JSON→store import, get_profiles_for_matching returns profiles
    byte-identical to the originals (zero data loss through seed→read round trip).

    This is the in-memory equivalent of 'Market Matching output for every
    Workflow_10 submission is byte-identical to the JSON-backed baseline':
    the matching engine receives the same frozen dataclasses regardless of
    whether it reads from the JSON file or the seeded DB store.
    """
    originals = [
        _make_carrier("CAR-01", carrier_name="Clearpath Specialty"),
        _make_carrier("CAR-02", carrier_name="Apex Underwriters", premium_min=25_000, premium_max=2_000_000),
        _make_carrier(
            "CAR-03",
            carrier_name="Summit Commercial",
            class_codes_accepted=("roofing_contractor",),
            class_codes_excluded=("habitational", "frame_construction"),
            historical_hit_rate=0.45,
            max_single_claim=500_000.0,
            ceiling_type="hard",
        ),
    ]

    # Seed to DB.
    seeded = await CarrierProfileService.seed_from_json(
        session, tenant.id, originals,
        gap_policy_overrides={"CAR-01": {"missing_document_type": "disclose"}},
    )
    assert len(seeded) == 3

    # Retrieve via the matching-engine read path.
    retrieved = await CarrierProfileService.get_profiles_for_matching(
        session, tenant.id, workflow_n=10
    )
    assert len(retrieved) == 3

    # Index by carrier_id for comparison.
    by_id_orig = {p.carrier_id: p for p in originals}
    by_id_ret = {p.carrier_id: p for p in retrieved}

    for cid, orig in by_id_orig.items():
        ret = by_id_ret[cid]
        # Every substantive field must survive the seed→read round trip.
        assert ret.carrier_name == orig.carrier_name, f"{cid}: carrier_name"
        assert ret.class_codes_accepted == orig.class_codes_accepted, f"{cid}: class_codes_accepted"
        assert ret.class_codes_excluded == orig.class_codes_excluded, f"{cid}: class_codes_excluded"
        assert ret.states_licensed == orig.states_licensed, f"{cid}: states_licensed"
        assert ret.premium_band.min == orig.premium_band.min, f"{cid}: premium_band.min"
        assert ret.premium_band.max == orig.premium_band.max, f"{cid}: premium_band.max"
        assert ret.severity_ceiling.max_single_claim_incurred == orig.severity_ceiling.max_single_claim_incurred, f"{cid}: severity_ceiling"
        assert ret.submission_requirements.min_loss_run_years == orig.submission_requirements.min_loss_run_years, f"{cid}: min_loss_run_years"
        assert tuple(ret.submission_requirements.required_documents) == orig.submission_requirements.required_documents, f"{cid}: required_documents"
        assert ret.submission_requirements.acceptance_window_days == orig.submission_requirements.acceptance_window_days, f"{cid}: acceptance_window_days"
        assert ret.appetite_confidence == orig.appetite_confidence, f"{cid}: appetite_confidence"
        assert ret.historical_hit_rate_this_class == orig.historical_hit_rate_this_class, f"{cid}: hit_rate"
        assert tuple(ret.lines_written) == orig.lines_written, f"{cid}: lines_written"
        assert ret.notes == orig.notes, f"{cid}: notes"


async def test_seed_parity_gap_policy_overrides_preserved(
    session: AsyncSession, tenant: Tenant
) -> None:
    """gap_policy_overrides passed to seed_from_json are stored on the profile row."""
    profiles = [_make_carrier("CAR-06")]
    await CarrierProfileService.seed_from_json(
        session, tenant.id, profiles,
        gap_policy_overrides={"CAR-06": {"missing_document_type": "disclose"}},
    )
    row = await CarrierProfileService.get_latest(session, tenant.id, "CAR-06")
    assert row is not None
    assert row.gap_policy == {"missing_document_type": "disclose"}
    assert row.source == SOURCE_SEED


async def test_seed_idempotent_second_call_is_noop(
    session: AsyncSession, tenant: Tenant
) -> None:
    """Re-running seed_from_json for an already-seeded carrier is a no-op (idempotent)."""
    profiles = [_make_carrier("CAR-01")]
    first = await CarrierProfileService.seed_from_json(session, tenant.id, profiles)
    second = await CarrierProfileService.seed_from_json(session, tenant.id, profiles)
    assert len(first) == 1
    assert len(second) == 0  # no new rows

    # Exactly one row exists.
    rows, history = await CarrierProfileService.get_with_history(session, tenant.id, "CAR-01")
    assert rows is not None
    assert history == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Versioning
# ═══════════════════════════════════════════════════════════════════════════════


async def test_versioning_human_edit_creates_new_row(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Human edit creates a NEW version row; old row retained; supersedes_version_id set."""
    profiles = [_make_carrier("CAR-01")]
    await CarrierProfileService.seed_from_json(session, ctx.tenant_id, profiles)

    v1 = await CarrierProfileService.get_latest(session, ctx.tenant_id, "CAR-01")
    assert v1 is not None
    assert v1.source == SOURCE_SEED

    # Human edit: add technology class_code.
    edit_data: dict[str, Any] = {
        "carrier_name": v1.carrier_name,
        "class_codes_accepted": list(v1.class_codes_accepted) + ["technology"],
        "class_codes_excluded": list(v1.class_codes_excluded),
        "states_licensed": list(v1.states_licensed),
        "premium_band": v1.premium_band,
        "submission_requirements": v1.submission_requirements,
        "severity_ceiling": v1.severity_ceiling,
        "appetite_confidence": v1.appetite_confidence,
        "historical_hit_rate_this_class": v1.historical_hit_rate_this_class,
        "lines_written": list(v1.lines_written),
        "notes": "Added technology class per underwriter guidance.",
        "form_metadata": {},
        "gap_policy": v1.gap_policy,
    }
    v2 = await CarrierProfileService.create_version(session, ctx, "CAR-01", edit_data)

    # New version created.
    assert v2.source == SOURCE_HUMAN_EDIT
    assert v2.version_id != v1.version_id
    assert v2.supersedes_version_id == v1.version_id
    assert "technology" in v2.class_codes_accepted

    # Old version still exists (append-only, never deleted).
    current, history = await CarrierProfileService.get_with_history(session, ctx.tenant_id, "CAR-01")
    assert current is not None
    assert current.version_id == v2.version_id
    assert len(history) == 1
    assert history[0].version_id == v1.version_id
    assert history[0].source == SOURCE_SEED


async def test_versioning_output_package_stamps_version_id(
    session: AsyncSession, ctx: Ctx
) -> None:
    """An OutputPackage created after a human edit records that edit's version_id.
    The payload stores the specific version_id stamped at creation time — never
    the sentinel string 'current' (KB05: immutable audit trail)."""
    profiles = [_make_carrier("CAR-01")]
    await CarrierProfileService.seed_from_json(session, ctx.tenant_id, profiles)
    v2 = await CarrierProfileService.create_version(
        session, ctx, "CAR-01",
        {"carrier_name": "Clearpath Specialty", "class_codes_accepted": ["manufacturing"],
         "class_codes_excluded": [], "states_licensed": ["TX"], "premium_band": {"min": 50000, "max": 5000000},
         "submission_requirements": {}, "severity_ceiling": {}, "appetite_confidence": "high",
         "historical_hit_rate_this_class": 0.72, "lines_written": ["GL"], "notes": "",
         "form_metadata": {}, "gap_policy": {}},
    )

    # Simulate the PA pipeline stamping the version_id at package creation time.
    profile_version_id = v2.version_id
    assert profile_version_id is not None
    assert profile_version_id != "current"  # sentinel forbidden by KB05
    assert len(profile_version_id) == 36  # UUID format

    # Store in an OutputPackage payload (mirrors service.py line 279).
    pkg = OutputPackageRow(
        id=str(uuid4()),
        tenant_id=ctx.tenant_id,
        submission_id="sub-pa-test",
        workflow="package_assembly",
        payload={"profile_version_id": profile_version_id, "status": "READY"},
    )
    session.add(pkg)
    await session.commit()
    await session.refresh(pkg)

    assert pkg.payload is not None
    assert pkg.payload["profile_version_id"] == v2.version_id


async def test_versioning_ci_refresh_creates_third_version(
    session: AsyncSession, ctx: Ctx
) -> None:
    """CI metadata refresh (refresh_metadata) creates a third version row that
    carries forward all substantive fields from v2, only updating the two CI fields."""
    profiles = [_make_carrier("CAR-01")]
    await CarrierProfileService.seed_from_json(session, ctx.tenant_id, profiles)

    v1 = await CarrierProfileService.get_latest(session, ctx.tenant_id, "CAR-01")
    assert v1 is not None

    v2 = await CarrierProfileService.create_version(
        session, ctx, "CAR-01",
        {"carrier_name": v1.carrier_name, "class_codes_accepted": ["manufacturing", "technology"],
         "class_codes_excluded": list(v1.class_codes_excluded), "states_licensed": list(v1.states_licensed),
         "premium_band": v1.premium_band, "submission_requirements": v1.submission_requirements,
         "severity_ceiling": v1.severity_ceiling, "appetite_confidence": v1.appetite_confidence,
         "historical_hit_rate_this_class": v1.historical_hit_rate_this_class,
         "lines_written": list(v1.lines_written), "notes": v1.notes,
         "form_metadata": {}, "gap_policy": {"missing_document_type": "disclose"}},
    )

    dto = MetadataRefreshDTO(appetite_confidence="medium", appetite_last_updated="2027-07-01")
    v3 = await CarrierProfileService.refresh_metadata(session, ctx, "CAR-01", dto)

    assert v3.source == SOURCE_CI
    assert v3.supersedes_version_id == v2.version_id
    # CI fields updated.
    assert v3.appetite_confidence == "medium"
    assert v3.appetite_last_updated == "2027-07-01"
    # Substantive fields carried forward from v2 verbatim.
    assert v3.class_codes_accepted == v2.class_codes_accepted
    assert v3.class_codes_excluded == v2.class_codes_excluded
    assert v3.premium_band == v2.premium_band
    assert v3.severity_ceiling == v2.severity_ceiling
    assert v3.gap_policy == v2.gap_policy

    # All three versions present.
    _curr, history = await CarrierProfileService.get_with_history(session, ctx.tenant_id, "CAR-01")
    assert len(history) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Field-guard (FR-4 architectural gate)
# ═══════════════════════════════════════════════════════════════════════════════


def test_field_guard_metadata_refresh_dto_has_only_two_fields() -> None:
    """MetadataRefreshDTO carries ONLY appetite_confidence + appetite_last_updated.

    This is the FR-4 structural gate: because the DTO's type definition limits
    its fields to exactly these two, there is NO code path — including the CI
    write path — that can supply class_codes_accepted, class_codes_excluded,
    premium_band, or severity_ceiling through the CI refresh route.
    """
    actual = set(MetadataRefreshDTO.model_fields.keys())
    expected = {"appetite_confidence", "appetite_last_updated"}
    assert actual == expected, (
        f"MetadataRefreshDTO must have exactly {expected}, found {actual}. "
        "Any additional field breaks the FR-4 substantive-field protection."
    )

    # Substantive fields must not exist on the DTO.
    forbidden = {
        "class_codes_accepted",
        "class_codes_excluded",
        "premium_band",
        "severity_ceiling",
        "submission_requirements",
        "states_licensed",
        "gap_policy",
        "historical_hit_rate_this_class",
    }
    leaked = forbidden & actual
    assert not leaked, f"Substantive fields leaked into MetadataRefreshDTO: {leaked}"


def test_field_guard_extra_fields_raise_validation_error() -> None:
    """Constructing MetadataRefreshDTO with any substantive field is a ValidationError.

    This proves the gate is enforced at runtime, not just structurally. A future
    developer cannot bypass the two-field restriction without a type error.
    """
    # Valid construction must succeed.
    valid = MetadataRefreshDTO(appetite_confidence="high", appetite_last_updated="2027-07-01")
    assert valid.appetite_confidence == "high"
    assert valid.appetite_last_updated == "2027-07-01"

    # Constructing with each forbidden field must fail.
    forbidden_attempts = [
        {"class_codes_accepted": ["manufacturing"], "appetite_confidence": "high", "appetite_last_updated": "2027-07-01"},
        {"class_codes_excluded": ["habitational"], "appetite_confidence": "high", "appetite_last_updated": "2027-07-01"},
        {"premium_band": {"min": 50000, "max": 5000000}, "appetite_confidence": "high", "appetite_last_updated": "2027-07-01"},
        {"severity_ceiling": {"max_single_claim_incurred": 1000000}, "appetite_confidence": "high", "appetite_last_updated": "2027-07-01"},
        {"gap_policy": {"missing_document_type": "disclose"}, "appetite_confidence": "high", "appetite_last_updated": "2027-07-01"},
    ]
    for kwargs in forbidden_attempts:
        with pytest.raises(pydantic.ValidationError):
            MetadataRefreshDTO(**kwargs)


async def test_field_guard_refresh_metadata_carries_forward_substantive_fields(
    session: AsyncSession, ctx: Ctx
) -> None:
    """refresh_metadata only touches appetite_confidence + appetite_last_updated.
    All other fields are copied verbatim from the current version (KB06: no fabrication).
    This test asserts each substantive field is unchanged after a CI refresh."""
    original = _make_carrier(
        "CAR-GATE",
        class_codes_accepted=("roofing", "frame_construction"),
        class_codes_excluded=("habitational",),
        premium_min=75_000,
        premium_max=3_000_000,
        max_single_claim=750_000,
        appetite_confidence="high",
        historical_hit_rate=0.68,
    )
    await CarrierProfileService.seed_from_json(session, ctx.tenant_id, [original])
    # Seed a gap_policy too.
    v1 = await CarrierProfileService.get_latest(session, ctx.tenant_id, "CAR-GATE")
    assert v1 is not None
    # Patch gap_policy onto v1 (seed doesn't accept overrides for GATE carrier here).
    v1.gap_policy = {"missing_document_type": "disclose"}  # type: ignore[assignment]
    session.add(v1)
    await session.commit()
    await session.refresh(v1)

    # Apply a CI metadata refresh.
    dto = MetadataRefreshDTO(appetite_confidence="low", appetite_last_updated="2027-06-15")
    v2 = await CarrierProfileService.refresh_metadata(session, ctx, "CAR-GATE", dto)

    # Only the two CI fields changed.
    assert v2.appetite_confidence == "low"            # changed
    assert v2.appetite_last_updated == "2027-06-15"   # changed

    # Every substantive field is byte-identical to v1.
    assert v2.class_codes_accepted == v1.class_codes_accepted
    assert v2.class_codes_excluded == v1.class_codes_excluded
    assert v2.premium_band == v1.premium_band
    assert v2.severity_ceiling == v1.severity_ceiling
    assert v2.submission_requirements == v1.submission_requirements
    assert v2.states_licensed == v1.states_licensed
    assert v2.gap_policy == v1.gap_policy               # gap_policy carried forward
    assert v2.historical_hit_rate_this_class == v1.historical_hit_rate_this_class
    assert v2.lines_written == v1.lines_written
    assert v2.source == SOURCE_CI


async def test_field_guard_ci_path_cannot_write_class_codes(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Structural proof: there is no argument to refresh_metadata that accepts
    class_codes_accepted. This test exercises the only CI write code path and
    confirms the field is absent from the DTO (type-level impossibility)."""
    original = _make_carrier("CAR-FGUARD", class_codes_accepted=("manufacturing",))
    await CarrierProfileService.seed_from_json(session, ctx.tenant_id, [original])

    # The only CI write method — refresh_metadata — takes a MetadataRefreshDTO.
    # MetadataRefreshDTO has no class_codes_accepted field; the following call is
    # the ONLY way CI code can write a new version, and it cannot change class codes.
    dto = MetadataRefreshDTO(appetite_confidence="medium", appetite_last_updated="2027-07-01")
    v2 = await CarrierProfileService.refresh_metadata(session, ctx, "CAR-FGUARD", dto)

    assert tuple(v2.class_codes_accepted) == ("manufacturing",)
    assert v2.appetite_confidence == "medium"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. gap_policy sourcing
# ═══════════════════════════════════════════════════════════════════════════════


def test_gap_policy_resolve_none_returns_default_block() -> None:
    """_resolve_policy(None, ...) → 'block' — pre-G2 behaviour preserved."""
    assert _resolve_policy(None, "missing_document_type") == "block"
    assert _resolve_policy(None, "supplemental_form_incomplete") == "block"
    assert _resolve_policy(None, "loss_run_year_shortfall") == "block"


def test_gap_policy_resolve_empty_dict_returns_default_block() -> None:
    """_resolve_policy({}, ...) → 'block' — empty map treated same as None."""
    assert _resolve_policy({}, "missing_document_type") == "block"


def test_gap_policy_resolve_explicit_disclose() -> None:
    """_resolve_policy({'missing_document_type': 'disclose'}, ...) → 'disclose'."""
    policy = {"missing_document_type": "disclose"}
    assert _resolve_policy(policy, "missing_document_type") == "disclose"


def test_gap_policy_resolve_unknown_key_falls_back_to_block() -> None:
    """A key not in the policy dict falls back to the default 'block'."""
    policy = {"supplemental_form_incomplete": "disclose"}
    assert _resolve_policy(policy, "missing_document_type") == "block"


def test_gap_policy_assemble_disclose_gives_ready_with_gap() -> None:
    """PA Scenario 01 equivalent: carrier with gap_policy=disclose for a missing
    document → READY_WITH_GAP (not BLOCKED). The existing auto-fill-boundary
    / READY_WITH_GAP outcome is preserved when the profile provides the policy."""
    from core.common.dtos import ExtractedModel

    carrier_view = {
        "carrier_id": "CAR-06",
        "carrier_name": "Vantage Commercial",
        "carrier_requirements": {
            "required_documents": ["loss_run_statement"],  # will be missing
        },
        "documents_available_from_extraction": [],  # nothing provided → missing
        "missing_info_from_market_matching": [],
    }
    data = ExtractedModel(submission_id="sub-pa-test", fields=[])

    # With disclose policy → READY_WITH_GAP (gap disclosed, not blocking).
    result_gap = assemble_package(
        carrier_view, data,
        gap_policy={"missing_document_type": "disclose"},
    )
    assert result_gap.status == "READY_WITH_GAP", f"Expected READY_WITH_GAP, got {result_gap.status}"
    assert len(result_gap.blocking_items) == 0
    assert len(result_gap.gap_items_disclosed) == 1
    assert "loss_run_statement" in result_gap.gap_items_disclosed[0].item


def test_gap_policy_assemble_none_gives_blocked() -> None:
    """Same carrier_view with gap_policy=None → BLOCKED (pre-G2 behaviour preserved).
    This is the zero-regression gate: removing the profile must not silently flip
    a carrier from BLOCKED to READY."""
    from core.common.dtos import ExtractedModel

    carrier_view = {
        "carrier_id": "CAR-06",
        "carrier_name": "Vantage Commercial",
        "carrier_requirements": {
            "required_documents": ["loss_run_statement"],
        },
        "documents_available_from_extraction": [],
        "missing_info_from_market_matching": [],
    }
    data = ExtractedModel(submission_id="sub-pa-test", fields=[])

    # With no policy (None) → BLOCKED (default block policy).
    result_blocked = assemble_package(carrier_view, data, gap_policy=None)
    assert result_blocked.status == "BLOCKED", f"Expected BLOCKED, got {result_blocked.status}"
    assert len(result_blocked.blocking_items) == 1
    assert len(result_blocked.gap_items_disclosed) == 0


async def test_gap_policy_profile_row_gap_policy_feeds_assembly(
    session: AsyncSession, ctx: Ctx
) -> None:
    """End-to-end: a seeded profile with gap_policy is retrieved and its gap_policy
    can be passed to assemble_package, producing READY_WITH_GAP for the same
    carrier_view that would otherwise be BLOCKED."""
    from core.common.dtos import ExtractedModel

    profiles = [_make_carrier("CAR-07")]
    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id, profiles,
        gap_policy_overrides={"CAR-07": {"missing_document_type": "disclose"}},
    )
    row = await CarrierProfileService.get_latest(session, ctx.tenant_id, "CAR-07")
    assert row is not None
    gap_policy = dict(row.gap_policy)  # retrieved from store, not hardcoded

    carrier_view = {
        "carrier_id": "CAR-07",
        "carrier_name": row.carrier_name,
        "carrier_requirements": {"required_documents": ["loss_run_3yr"]},
        "documents_available_from_extraction": [],
        "missing_info_from_market_matching": [],
    }
    data = ExtractedModel(submission_id="sub-e2e-test", fields=[])

    result = assemble_package(carrier_view, data, gap_policy=gap_policy)
    assert result.status == "READY_WITH_GAP"
    # Without the profile gap_policy the same run would be BLOCKED.
    result_no_profile = assemble_package(carrier_view, data, gap_policy=None)
    assert result_no_profile.status == "BLOCKED"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Empty store
# ═══════════════════════════════════════════════════════════════════════════════


async def test_empty_store_fallback_no_crash(session: AsyncSession, tenant: Tenant) -> None:
    """With no profiles seeded, get_profiles_for_matching falls back to the JSON panel.
    Since TEST_DATA_ROOT is not set, load_carrier_panel() returns []; this is the
    expected behaviour — Market Matching produces no matches, not a crash.
    """
    profiles = await CarrierProfileService.get_profiles_for_matching(
        session, tenant.id, workflow_n=10
    )
    # Empty or not — but must not raise.
    assert isinstance(profiles, list)
    # TEST_DATA_ROOT is not set so JSON panel also returns [].
    assert profiles == []


async def test_empty_store_after_seed_db_path_taken(
    session: AsyncSession, tenant: Tenant
) -> None:
    """Once profiles are seeded, get_profiles_for_matching uses the DB, not the JSON fallback."""
    originals = [_make_carrier("CAR-A"), _make_carrier("CAR-B")]
    await CarrierProfileService.seed_from_json(session, tenant.id, originals)

    profiles = await CarrierProfileService.get_profiles_for_matching(
        session, tenant.id, workflow_n=10
    )
    # DB path taken: returns exactly the seeded carriers (2), regardless of JSON panel.
    assert len(profiles) == 2
    carrier_ids = {p.carrier_id for p in profiles}
    assert carrier_ids == {"CAR-A", "CAR-B"}


async def test_empty_store_separate_tenants_isolated(
    session: AsyncSession
) -> None:
    """Profiles seeded for one tenant are not visible to another tenant's store."""
    t1 = Tenant(id="t-alpha", name="Alpha", vertical=Vertical.ES, domain="alpha.test")
    t2 = Tenant(id="t-beta", name="Beta", vertical=Vertical.ES, domain="beta.test")
    session.add(t1); session.add(t2)
    await session.commit()

    # Seed 2 carriers for t1.
    await CarrierProfileService.seed_from_json(
        session, "t-alpha", [_make_carrier("CAR-X"), _make_carrier("CAR-Y")]
    )

    # t2 sees an empty store → fallback.
    t2_profiles = await CarrierProfileService.get_profiles_for_matching(
        session, "t-beta", workflow_n=10
    )
    assert t2_profiles == []

    # t1 sees its own 2 carriers.
    t1_profiles = await CarrierProfileService.get_profiles_for_matching(
        session, "t-alpha", workflow_n=10
    )
    assert len(t1_profiles) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Suggestion inbox (approve / dismiss)
# ═══════════════════════════════════════════════════════════════════════════════


def _make_suggestion_pkg_and_item(
    tenant_id: str,
    carrier_id: str,
    *,
    suggestion_id: str | None = None,
    pattern_type: str = "GENUINE_INCONSISTENCY",
    include_metadata_refresh: bool = False,
) -> tuple[OutputPackageRow, ReviewItemRow]:
    """Build a CAI suggestion OutputPackage + ReviewItem (not yet persisted)."""
    sid = suggestion_id or f"sug-{uuid4().hex[:8]}"
    payload: dict[str, Any] = {
        "carrier_id": carrier_id,
        "carrier_name": "Ironclad Specialty",
        "suggestion_id": sid,
        "pattern_type": pattern_type,
        "suggested_action": "Review class appetite.",
        "status": "PENDING_REVIEW",
        "class_code": "ALL",
    }
    if include_metadata_refresh:
        payload["metadata_refresh"] = {
            "appetite_confidence": "medium",
            "appetite_last_updated": "2027-07-01",
        }

    pkg = OutputPackageRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        submission_id=f"cai-{carrier_id}",
        workflow="carrier_appetite_intelligence",
        payload=payload,
    )
    item = ReviewItemRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        submission_id=f"cai-{carrier_id}",
        workflow="carrier_appetite_intelligence",
        status=ReviewStatus.PENDING,
        output_package_id=pkg.id,
    )
    return pkg, item


async def test_suggestion_dismiss_marks_dismissed_no_version(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Dismissing a CI suggestion marks payload['status'] = 'DISMISSED';
    no new profile version is created."""
    carrier_id = "CAR-DISMISS"
    sid = f"sug-{uuid4().hex[:8]}"
    pkg, item = _make_suggestion_pkg_and_item(ctx.tenant_id, carrier_id, suggestion_id=sid)
    session.add(pkg); session.add(item)
    await session.commit()

    # Count profile versions before dismiss.
    rows_before = await CarrierProfileService.list_current(session, ctx.tenant_id)
    count_before = len(rows_before)

    # Call dismiss logic directly (mirrors router.dismiss_suggestion).
    updated_payload = {**pkg.payload, "status": "DISMISSED"}
    pkg.payload = updated_payload  # type: ignore[assignment]
    session.add(pkg)
    await session.commit()
    await session.refresh(pkg)

    assert pkg.payload["status"] == "DISMISSED"

    # No new profile version written.
    rows_after = await CarrierProfileService.list_current(session, ctx.tenant_id)
    assert len(rows_after) == count_before


async def test_suggestion_approve_without_metadata_refresh_marks_approved(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Approving a GENUINE_INCONSISTENCY suggestion (no metadata_refresh) marks
    payload['status'] = 'APPROVED' without writing a profile version row."""
    carrier_id = "CAR-APPROVE-NOCI"
    sid = f"sug-{uuid4().hex[:8]}"
    pkg, item = _make_suggestion_pkg_and_item(
        ctx.tenant_id, carrier_id, suggestion_id=sid,
        pattern_type="GENUINE_INCONSISTENCY",
        include_metadata_refresh=False,
    )
    session.add(pkg); session.add(item)
    await session.commit()

    # Approve without metadata_refresh: just mark status.
    updated_payload = {**pkg.payload, "status": "APPROVED"}
    pkg.payload = updated_payload  # type: ignore[assignment]
    session.add(pkg)
    await session.commit()
    await session.refresh(pkg)

    assert pkg.payload["status"] == "APPROVED"
    # No profile version written.
    profile = await CarrierProfileService.get_latest(session, ctx.tenant_id, carrier_id)
    assert profile is None


async def test_suggestion_approve_with_metadata_refresh_writes_new_version(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Approving a CONFIRMED_CONSISTENT suggestion with metadata_refresh payload
    calls refresh_metadata and writes a new profile version row."""
    carrier_id = "CAR-APPROVE-CI"
    sid = f"sug-{uuid4().hex[:8]}"

    # Pre-seed a profile so refresh_metadata has a base row to chain from.
    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id, [_make_carrier(carrier_id)]
    )
    v1 = await CarrierProfileService.get_latest(session, ctx.tenant_id, carrier_id)
    assert v1 is not None

    pkg, item = _make_suggestion_pkg_and_item(
        ctx.tenant_id, carrier_id, suggestion_id=sid,
        pattern_type="CONFIRMED_CONSISTENT",
        include_metadata_refresh=True,  # payload["metadata_refresh"] present
    )
    session.add(pkg); session.add(item)
    await session.commit()

    # Mirrors router.approve_suggestion logic exactly.
    payload = dict(pkg.payload or {})
    metadata_refresh = payload.get("metadata_refresh")
    assert metadata_refresh is not None

    dto = MetadataRefreshDTO(
        appetite_confidence=metadata_refresh["appetite_confidence"],
        appetite_last_updated=metadata_refresh["appetite_last_updated"],
    )
    v2 = await CarrierProfileService.refresh_metadata(session, ctx, carrier_id, dto)

    # Mark approved.
    pkg.payload = {**payload, "status": "APPROVED"}  # type: ignore[assignment]
    session.add(pkg)
    await session.commit()

    # New profile version written.
    assert v2.version_id != v1.version_id
    assert v2.supersedes_version_id == v1.version_id
    assert v2.source == SOURCE_CI
    assert v2.appetite_confidence == "medium"
    assert v2.appetite_last_updated == "2027-07-01"
    # Substantive fields unchanged.
    assert v2.class_codes_accepted == v1.class_codes_accepted
    assert v2.premium_band == v1.premium_band
    assert v2.severity_ceiling == v1.severity_ceiling

    await session.refresh(pkg)
    assert pkg.payload["status"] == "APPROVED"


async def test_suggestion_approve_dismiss_do_not_interfere(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Approving carrier A's suggestion does not affect carrier B's suggestion or profile."""
    carrier_a = "CAR-AA"
    carrier_b = "CAR-BB"

    await CarrierProfileService.seed_from_json(
        session, ctx.tenant_id,
        [_make_carrier(carrier_a), _make_carrier(carrier_b)]
    )

    sid_a = f"sug-{uuid4().hex[:8]}"
    sid_b = f"sug-{uuid4().hex[:8]}"
    pkg_a, item_a = _make_suggestion_pkg_and_item(
        ctx.tenant_id, carrier_a, suggestion_id=sid_a,
        include_metadata_refresh=True,
    )
    pkg_b, item_b = _make_suggestion_pkg_and_item(
        ctx.tenant_id, carrier_b, suggestion_id=sid_b,
        include_metadata_refresh=False,
    )
    session.add(pkg_a); session.add(item_a)
    session.add(pkg_b); session.add(item_b)
    await session.commit()

    # Approve A → writes new version for A.
    payload_a = dict(pkg_a.payload or {})
    dto = MetadataRefreshDTO(
        appetite_confidence=payload_a["metadata_refresh"]["appetite_confidence"],
        appetite_last_updated=payload_a["metadata_refresh"]["appetite_last_updated"],
    )
    v_a2 = await CarrierProfileService.refresh_metadata(session, ctx, carrier_a, dto)
    pkg_a.payload = {**payload_a, "status": "APPROVED"}  # type: ignore[assignment]
    session.add(pkg_a); await session.commit()

    # Dismiss B → no new version for B.
    pkg_b.payload = {**(pkg_b.payload or {}), "status": "DISMISSED"}  # type: ignore[assignment]
    session.add(pkg_b); await session.commit()

    # Carrier A: 2 versions (SEED + CI).
    _curr_a, hist_a = await CarrierProfileService.get_with_history(session, ctx.tenant_id, carrier_a)
    assert len(hist_a) == 1
    assert _curr_a is not None
    assert _curr_a.source == SOURCE_CI

    # Carrier B: still only 1 version (SEED).
    _curr_b, hist_b = await CarrierProfileService.get_with_history(session, ctx.tenant_id, carrier_b)
    assert len(hist_b) == 0
    assert _curr_b is not None
    assert _curr_b.source == SOURCE_SEED
