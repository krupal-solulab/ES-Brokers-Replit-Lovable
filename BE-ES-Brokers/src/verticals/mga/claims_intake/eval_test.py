"""Eval — Claims Intake Coordination against the real Workflow-10 dataset
(``Data sets/Workflow-10/claims_intake_dataset``), same convention as every other
MGA workflow's eval suite: assert against each scenario's real ``expected_output.txt``
outcome, not hand-authored placeholder data.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, col, select

import core.models  # noqa: F401  (register shared tables)
from core.common.dtos import Ctx
from core.common.enums import Role, Vertical
from core.models import ReviewItem, Tenant
from core.review_queue import AuthorityError
from verticals.mga.claims_intake.fixtures import list_scenarios
from verticals.mga.claims_intake.service import WORKFLOW, ClaimsIntakeService
from verticals.mga.models import MgaClaimsIntakeResult

pytestmark = pytest.mark.skipif(
    not list_scenarios(), reason="Workflow-10 real dataset not found")

EXPECTED = {
    "scenario_01": {"authority": "WITHIN_AUTHORITY", "routing": "HANDLED_INTERNALLY",
                    "phi": "NOT_TRIGGERED", "within_ceiling": True},
    "scenario_02": {"authority": "WITHIN_AUTHORITY", "routing": "HANDLED_INTERNALLY",
                    "phi": "BLOCKED", "within_ceiling": None},
    "scenario_03": {"authority": "EXCEEDS_AUTHORITY", "routing": "REFERRED_EXCEEDS_AUTHORITY",
                    "phi": "PERMITTED", "within_ceiling": False},
    "scenario_04": {"authority": "NO_AUTHORITY_DELEGATED", "routing": "FORWARDED_NO_AUTHORITY",
                    "phi": "NOT_TRIGGERED", "within_ceiling": None},
    "scenario_05": {"authority": "WITHIN_AUTHORITY", "routing": "HANDLED_INTERNALLY",
                    "phi": "NOT_TRIGGERED", "within_ceiling": None},
    "scenario_06": {"authority": "WITHIN_AUTHORITY", "routing": "HANDLED_INTERNALLY",
                    "phi": "NOT_TRIGGERED", "within_ceiling": None},
}


@pytest.fixture
async def mem_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add(Tenant(id="demo-mga", name="Demo MGA", vertical=Vertical.MGA))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.fixture
def mga_ctx() -> Ctx:
    return Ctx(tenant_id="demo-mga", vertical=Vertical.MGA, user_id="u-jr", role=Role.JUNIOR)


async def test_all_six_scenarios_match_expected_outcome(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    svc = ClaimsIntakeService()
    for ref, expected in EXPECTED.items():
        d = await svc.process(mem_session, mga_ctx, ref)
        assert d.authorityClassification == expected["authority"], ref
        assert d.routingOutcome == expected["routing"], ref
        assert d.phiGate.medicalContentProcessingStatus == expected["phi"], ref
        assert d.settlementAuthorityCheck.withinCeiling == expected["within_ceiling"], ref


async def test_scenario_01_clean_property_damage_ready_internal(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await ClaimsIntakeService().process(mem_session, mga_ctx, "scenario_01")
    assert d.bodilyInjuryInvolved is False
    assert d.phiGate.triggered is False
    assert d.settlementAuthorityCheck.estimatedReserve == 4200.0
    assert d.settlementAuthorityCheck.ceiling == 25000.0
    assert d.status == "READY_FOR_INTERNAL_HANDLING"


async def test_scenario_02_phi_gate_hard_blocks_no_baa(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    """CLI-04 — the single most important rule in this PRD. No BAA, no processing,
    no bypass, regardless of how routine the underlying claim looks."""
    d = await ClaimsIntakeService().process(mem_session, mga_ctx, "scenario_02")
    assert d.phiGate.triggered is True
    assert d.phiGate.baaConfirmed is False
    assert d.phiGate.medicalContentProcessingStatus == "BLOCKED"
    assert d.status == "PHI_BLOCKED"


async def test_scenario_03_exceeds_authority_never_handled_as_within(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await ClaimsIntakeService().process(mem_session, mga_ctx, "scenario_03")
    assert d.phiGate.baaConfirmed is True  # BAA is signed here — distinct from scenario_02
    assert d.settlementAuthorityCheck.estimatedReserve == 175_000.0
    assert d.settlementAuthorityCheck.ceiling == 50_000.0
    assert d.settlementAuthorityCheck.withinCeiling is False
    assert d.authorityClassification == "EXCEEDS_AUTHORITY"
    assert d.status == "MUST_REFER"


async def test_scenario_04_no_authority_never_conflated_with_exceeds(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    """CLI-01's hardest requirement: "authority exists but exceeded" (scenario_03) and
    "no authority ever delegated" (this scenario) must never collapse into the same
    classification or routing outcome."""
    d3 = await ClaimsIntakeService().process(mem_session, mga_ctx, "scenario_03")
    d4 = await ClaimsIntakeService().process(mem_session, mga_ctx, "scenario_04")
    assert d4.authorityClassification == "NO_AUTHORITY_DELEGATED"
    assert d4.routingOutcome == "FORWARDED_NO_AUTHORITY"
    assert d4.authorityClassification != d3.authorityClassification
    assert d4.routingOutcome != d3.routingOutcome
    assert d4.status == "FORWARD_ONLY"


async def test_scenario_05_write_back_carries_real_claim_number(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await ClaimsIntakeService().process(mem_session, mga_ctx, "scenario_05")
    assert d.writeBackRecord.logged is True
    assert d.writeBackRecord.bordereauSchemaValidated is True
    assert d.writeBackRecord.claimNumber == "MCI-2027-99201"


async def test_scenario_06_procedural_signal_logged_never_alters_routing(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await ClaimsIntakeService().process(mem_session, mga_ctx, "scenario_06")
    assert len(d.proceduralSignals) == 2
    assert all(s.loggedOnly for s in d.proceduralSignals)
    # never characterized as fraud/suspicious language
    joined = " ".join(s.description.lower() for s in d.proceduralSignals)
    assert "fraud" not in joined and "suspicious" not in joined
    assert d.routingOutcome == "HANDLED_INTERNALLY"
    assert d.status == "READY_FOR_INTERNAL_HANDLING"


async def test_persistence_and_rbac(mem_session: AsyncSession, mga_ctx: Ctx) -> None:
    svc = ClaimsIntakeService()
    scenarios = list(EXPECTED)
    for ref in scenarios:
        await svc.process(mem_session, mga_ctx, ref)
    rows = await svc.list_rows(mem_session, mga_ctx)
    assert len(rows) == len(scenarios)
    assert (
        await mem_session.execute(select(MgaClaimsIntakeResult))
    ).scalars().all().__len__() == len(scenarios)

    item = (await mem_session.execute(
        select(ReviewItem).where(col(ReviewItem.workflow) == WORKFLOW))).scalars().first()
    assert item is not None and item.submission_id is not None
    detail = await svc.get_detail(mem_session, mga_ctx, item.submission_id)
    assert detail is not None

    # junior may not 'send' (carrier/TPA dispatch, senior-only)
    with pytest.raises(AuthorityError):
        await svc.act(mem_session, mga_ctx, item.submission_id, "send")

    senior_ctx = mga_ctx.model_copy(update={"role": Role.SENIOR})
    sent = await svc.act(mem_session, senior_ctx, item.submission_id, "send")
    assert sent["status"] == "sent"


async def test_unknown_scenario_raises_keyerror(mem_session: AsyncSession, mga_ctx: Ctx) -> None:
    with pytest.raises(KeyError):
        await ClaimsIntakeService().process(mem_session, mga_ctx, "does-not-exist")
