"""Eval — Portfolio & Book Performance Reporting against all 6 REAL Workflow-08
scenarios vs. their expected_output.txt outcomes. Fixtures loaded via
``fixtures.load_scenario`` — never hardcoded here. Skips cleanly if the dataset isn't
present on this machine.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, col, select

import core.models  # noqa: F401  (register shared tables)
from core.common.dtos import Ctx
from core.common.enums import Role, Vertical
from core.models import OutputPackage, ReviewItem, Submission, Tenant
from core.review_queue import AuthorityError
from verticals.mga.models import MgaBindResult, MgaGovernanceResult, MgaPortfolioResult, MgaPremiumLedger
from verticals.mga.portfolio_reporting.fixtures import dataset_dir
from verticals.mga.portfolio_reporting.service import WORKFLOW, PortfolioService

pytestmark = pytest.mark.skipif(
    dataset_dir() is None,
    reason="Workflow-08 dataset not found under 'Data sets/Workflow-08/"
    "mga_portfolio_reporting_dataset'",
)

EXPECTED = {
    "scenario_01": "READY",
    "scenario_02": "FLAGGED",
    "scenario_03": "READY",
    "scenario_04": "PARTIAL",
    "scenario_05": "READY",
    "scenario_06": "READY",
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


async def test_all_six_outcomes_match_spec(mem_session: AsyncSession, mga_ctx: Ctx) -> None:
    svc = PortfolioService()
    got: dict[str, str] = {}
    for ref in EXPECTED:
        detail = await svc.process(mem_session, mga_ctx, ref)
        got[ref] = detail.status
    assert got == EXPECTED, got


async def test_scenario_01_clean_baseline(mem_session: AsyncSession, mga_ctx: Ctx) -> None:
    d = await PortfolioService().process(mem_session, mga_ctx, "scenario_01")
    assert d.status == "READY"
    assert d.dataCompleteness.status == "COMPLETE"
    stages = {f.stage: f for f in d.funnel}
    assert stages["submitted"].count == 96
    assert stages["quoted"].pctOfPriorStage == 74.0
    assert stages["bound"].pctOfPriorStage == 76.1
    assert d.renewalRetention is not None
    assert d.renewalRetention.retentionRatePct == 86.8
    assert d.lossRatio is not None
    assert d.lossRatio.ratioPct == 40.0
    assert d.lossRatio.lowVolumeFlag is False


async def test_scenario_02_low_volume_single_event_flagged(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await PortfolioService().process(mem_session, mga_ctx, "scenario_02")
    assert d.status == "FLAGGED"
    assert d.lossRatio is not None
    assert d.lossRatio.ratioPct == 172.2
    assert d.lossRatio.lowVolumeFlag is True
    assert d.lossRatio.singleEventDrivenFlag is True
    # never presented as a bare percentage — must carry the trend/volume context
    assert "SINGLE" in d.lossRatio.detail
    assert "4 bound accounts" in d.lossRatio.detail


async def test_scenario_03_lapse_vs_non_renewal_never_collapsed(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await PortfolioService().process(mem_session, mga_ctx, "scenario_03")
    assert d.status == "READY"
    r = d.renewalRetention
    assert r is not None
    assert r.eligible == 3
    assert r.retained == 1
    assert r.nonRenewedUnderwritingDecision == 1
    assert r.lapsedNoDecision == 1
    categories = {item["policyNumber"]: item["category"] for item in r.lineItems}
    assert categories["APX-GL-88410"] == "RETAINED"
    assert categories["APX-GL-96065"] == "UNDERWRITING_NON_RENEWAL"
    assert categories["APX-GL-XXXX1"] == "LAPSED_NO_DECISION"


async def test_scenario_04_gap_cross_referenced_to_appetite_governance(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await PortfolioService().process(mem_session, mga_ctx, "scenario_04")
    assert d.status == "PARTIAL"
    assert d.dataCompleteness.status == "PARTIAL"
    assert len(d.dataCompleteness.gaps) == 1
    gap = d.dataCompleteness.gaps[0]
    assert gap.dateRange == "may"
    assert gap.crossReferencedFindingId is not None  # not treated as newly-discovered


async def test_scenario_05_broker_production_facts_only(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await PortfolioService().process(mem_session, mga_ctx, "scenario_05")
    assert d.status == "READY"
    by_broker = {b.brokerAgency: b for b in d.brokerProduction}
    assert by_broker["Coastal Insurance Brokers"].significantDecline is False
    assert by_broker["Liberty Line Insurance"].significantDecline is True
    # no speculative narrative in the per-broker detail — facts and framing only, never
    # an unevidenced theory about why a broker's production moved
    for forbidden in ("relationship strain", "competitive", "slow quarter"):
        assert forbidden not in by_broker["Liberty Line Insurance"].detail.lower()


async def test_scenario_06_appetite_exposure_pulled_not_recomputed(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await PortfolioService().process(mem_session, mga_ctx, "scenario_06")
    assert d.status == "READY"
    assert d.appetiteExposureSection is not None
    assert d.appetiteExposureSection.findingId == "AG-FIND-0091"
    assert d.appetiteExposureSection.lowVolumeFlag is True


async def _seed_output_package(session: AsyncSession, ctx: Ctx, workflow: str) -> Submission:
    sub = Submission(tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                     external_ref=f"seed-{workflow}", subject=f"seed-{workflow}",
                     status="seeded")
    session.add(sub)
    await session.flush()
    session.add(OutputPackage(tenant_id=ctx.tenant_id, submission_id=sub.id,
                              workflow=workflow, payload={}))
    await session.flush()
    return sub


async def test_run_full_book_report_reads_real_upstream_counts(
    mem_session: AsyncSession, mga_ctx: Ctx,
) -> None:
    """PBR-01/02 live: seed real Triage/Quoting/Bind activity plus a real bound
    premium ledger row, then confirm the live report reflects those counts, not a
    fixture and not zeros."""
    await _seed_output_package(mem_session, mga_ctx, "submission-triage")
    await _seed_output_package(mem_session, mga_ctx, "submission-triage")
    await _seed_output_package(mem_session, mga_ctx, "quoting-rating")
    bind_sub = await _seed_output_package(mem_session, mga_ctx, "bind-issuance")

    bind_result = MgaBindResult(
        tenant_id=mga_ctx.tenant_id, submission_id=bind_sub.id, status="READY",
        authority_outcome="WITHIN_AUTHORITY", issuance_status="NOT_YET_ISSUED",
        class_code="97047", carrier="Meridian Casualty Insurance Co.")
    mem_session.add(bind_result)
    await mem_session.flush()
    mem_session.add(MgaPremiumLedger(
        tenant_id=mga_ctx.tenant_id, submission_id=bind_sub.id,
        bind_result_id=bind_result.id, class_code="97047",
        carrier="Meridian Casualty Insurance Co.", premium=19845.0))
    await mem_session.commit()

    svc = PortfolioService()
    d = await svc.run_full_book_report(mem_session, mga_ctx, period="2027-Q3")
    stages = {f.stage: f for f in d.funnel}
    assert stages["submitted"].count == 2
    assert stages["quoted"].count == 1
    assert stages["bound"].count == 1
    assert d.lossRatio is not None
    assert d.lossRatio.earnedPremium == 19845.0
    # honest gap, never a fabricated retention rate — see live_aggregator.py
    assert d.renewalRetention is not None
    assert d.renewalRetention.eligible == 0
    assert d.renewalRetention.retained == 0


async def test_run_segment_loss_ratio_reads_real_ledger_rows(
    mem_session: AsyncSession, mga_ctx: Ctx,
) -> None:
    bind_sub = await _seed_output_package(mem_session, mga_ctx, "bind-issuance")
    bind_result = MgaBindResult(
        tenant_id=mga_ctx.tenant_id, submission_id=bind_sub.id, status="READY",
        issuance_status="NOT_YET_ISSUED", class_code="97047", carrier="Meridian")
    mem_session.add(bind_result)
    await mem_session.flush()
    mem_session.add(MgaPremiumLedger(
        tenant_id=mga_ctx.tenant_id, submission_id=bind_sub.id,
        bind_result_id=bind_result.id, class_code="97047", carrier="Meridian",
        premium=5000.0))
    await mem_session.commit()

    svc = PortfolioService()
    d = await svc.run_segment_loss_ratio(
        mem_session, mga_ctx, class_code="97047", period="2027-Q3")
    assert d.lossRatio is not None
    assert d.lossRatio.earnedPremium == 5000.0
    assert d.lossRatio.lowVolumeFlag is True  # 1 account is below the low-volume threshold


async def test_run_data_completeness_reads_real_activity_counts(
    mem_session: AsyncSession, mga_ctx: Ctx,
) -> None:
    await _seed_output_package(mem_session, mga_ctx, "submission-triage")
    await mem_session.commit()

    svc = PortfolioService()
    d = await svc.run_data_completeness(mem_session, mga_ctx, period="2027-08")
    assert d.dataCompleteness.status == "COMPLETE"


async def test_run_appetite_exposure_returns_404_with_no_live_finding(
    mem_session: AsyncSession, mga_ctx: Ctx,
) -> None:
    """No live AG-06 finding exists yet in a fresh DB — must fail honestly, never
    fabricate a finding to fill the section."""
    svc = PortfolioService()
    with pytest.raises(KeyError):
        await svc.run_appetite_exposure(mem_session, mga_ctx, period="2027-Q3")


async def test_run_appetite_exposure_pulls_real_governance_finding(
    mem_session: AsyncSession, mga_ctx: Ctx,
) -> None:
    gov_sub = await _seed_output_package(mem_session, mga_ctx, "appetite-governance")
    pkg = (await mem_session.execute(
        select(OutputPackage).where(col(OutputPackage.submission_id) == gov_sub.id))
    ).scalars().first()
    assert pkg is not None
    pkg.payload = {"detail": {"portfolioConcentrationFindings": [
        {"accountsNearCeiling": 2, "totalAccountsInSegment": 4, "lowVolumeFlag": True},
    ]}}
    mem_session.add(pkg)
    mem_session.add(MgaGovernanceResult(
        tenant_id=mga_ctx.tenant_id, submission_id=gov_sub.id, status="INFORMATIONAL",
        flagged_finding_count=1))
    await mem_session.commit()

    svc = PortfolioService()
    d = await svc.run_appetite_exposure(mem_session, mga_ctx, period="2027-Q3")
    assert d.appetiteExposureSection is not None
    assert d.appetiteExposureSection.lowVolumeFlag is True
    assert "2 of 4 accounts" in d.appetiteExposureSection.summary


async def test_persistence_and_rbac(mem_session: AsyncSession, mga_ctx: Ctx) -> None:
    svc = PortfolioService()
    for ref in EXPECTED:
        await svc.process(mem_session, mga_ctx, ref)
    rows = await svc.list_rows(mem_session, mga_ctx)
    assert len(rows) == 6
    assert (await mem_session.execute(select(MgaPortfolioResult))).scalars().all().__len__() == 6

    item = (await mem_session.execute(
        select(ReviewItem).where(col(ReviewItem.workflow) == WORKFLOW))).scalars().first()
    assert item is not None and item.submission_id is not None
    detail = await svc.get_detail(mem_session, mga_ctx, item.submission_id)
    assert detail is not None

    with pytest.raises(AuthorityError):  # junior may not 'send' (senior-only)
        await svc.act(mem_session, mga_ctx, item.submission_id, "send")

    senior_ctx = mga_ctx.model_copy(update={"role": Role.SENIOR})
    sent = await svc.act(mem_session, senior_ctx, item.submission_id, "send")
    assert sent["status"] == "sent"
