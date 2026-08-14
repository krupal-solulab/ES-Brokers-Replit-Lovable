"""Eval — Bordereau Reporting against all 6 REAL Workflow-09 scenarios vs. their
expected_output.txt outcomes. Fixtures loaded via ``fixtures.load_scenario`` — never
hardcoded here. Skips cleanly if the dataset isn't present on this machine.
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
from verticals.mga.bordereau_reporting.fixtures import dataset_dir
from verticals.mga.bordereau_reporting.service import WORKFLOW, BordereauService
from verticals.mga.models import MgaBordereauResult

pytestmark = pytest.mark.skipif(
    dataset_dir() is None,
    reason="Workflow-09 dataset not found under 'Data sets/Workflow-09/bordereau_dataset'",
)

EXPECTED = {
    "scenario_01": "READY_TO_SUBMIT",
    "scenario_02": "BLOCKED",
    "scenario_03": "BLOCKED",
    "scenario_04": "DISCREPANCY_FLAGGED",
    "scenario_05": "BLOCKED",
    "scenario_06": "URGENT_ALERT",
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
    svc = BordereauService()
    got: dict[str, str] = {}
    for ref in EXPECTED:
        detail = await svc.process(mem_session, mga_ctx, ref)
        got[ref] = detail.status
    assert got == EXPECTED, got


async def test_scenario_01_clean_baseline(mem_session: AsyncSession, mga_ctx: Ctx) -> None:
    d = await BordereauService().process(mem_session, mga_ctx, "scenario_01")
    assert d.status == "READY_TO_SUBMIT"
    assert d.completenessCheck.status == "COMPLETE"
    assert d.formatComplianceCheck.status == "COMPLIANT"
    assert d.reconciliationCheck.status == "MATCHED"
    assert d.dataCurrencyCheck.status == "CURRENT"


async def test_scenario_02_completeness_gap_missing_endorsement(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await BordereauService().process(mem_session, mga_ctx, "scenario_02")
    assert d.status == "BLOCKED"
    assert d.completenessCheck.status == "GAP_DETECTED"
    assert len(d.completenessCheck.missingTransactions) == 1
    assert "endorsement" in d.completenessCheck.missingTransactions[0].lower()


async def test_scenario_03_format_non_compliance_class_code_and_date(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await BordereauService().process(mem_session, mga_ctx, "scenario_03")
    assert d.status == "BLOCKED"
    assert d.formatComplianceCheck.status == "NON_COMPLIANT"
    assert len(d.formatComplianceCheck.issues) == 2
    issues_text = " ".join(d.formatComplianceCheck.issues).lower()
    assert "class code" in issues_text
    assert "date format" in issues_text


async def test_scenario_04_reconciliation_discrepancy_never_auto_resolved(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await BordereauService().process(mem_session, mga_ctx, "scenario_04")
    assert d.status == "DISCREPANCY_FLAGGED"
    assert d.reconciliationCheck.status == "DISCREPANCY"
    assert len(d.reconciliationCheck.discrepancyDetail) == 1
    # never defaults to either side — rationale must show investigation language, not
    # a silent resolution in favor of the MGA or the carrier
    assert "investigat" in d.rationale.lower()


async def test_scenario_05_stale_claims_data_blocked(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await BordereauService().process(mem_session, mga_ctx, "scenario_05")
    assert d.status == "BLOCKED"
    assert d.bordereauType == "CLAIMS"
    assert d.dataCurrencyCheck.status == "STALE_DATA_DETECTED"
    assert len(d.dataCurrencyCheck.staleItems) == 1
    assert "HM-2024-74810" in d.dataCurrencyCheck.staleItems[0]


async def test_scenario_06_urgent_timeliness_alert(
    mem_session: AsyncSession, mga_ctx: Ctx
) -> None:
    d = await BordereauService().process(mem_session, mga_ctx, "scenario_06")
    assert d.status == "URGENT_ALERT"
    assert d.timelinessCheck is not None
    assert d.timelinessCheck.daysRemaining == 3
    assert d.timelinessCheck.compilationTimeNeededDays == 3
    assert d.timelinessCheck.urgent is True


async def test_persistence_and_rbac(mem_session: AsyncSession, mga_ctx: Ctx) -> None:
    svc = BordereauService()
    for ref in EXPECTED:
        await svc.process(mem_session, mga_ctx, ref)
    rows = await svc.list_rows(mem_session, mga_ctx)
    assert len(rows) == 6
    assert (await mem_session.execute(select(MgaBordereauResult))).scalars().all().__len__() == 6

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
