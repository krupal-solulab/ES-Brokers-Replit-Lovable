"""Proves BrokerCopilotService.draft() is idempotent per (source_workflow,
submission_id) — a repeated "Draft to broker" click for the same source decision
must reuse the existing draft, not create a duplicate. This was a real bug: every
call unconditionally inserted a new MgaBrokerCommResult + OutputPackageRow +
ReviewItemRow, which is what inflated the draft queue to "34 drafts" on repeated
clicks/reloads. Self-contained (no TEST_DATA_ROOT fixture dependency, unlike
broker_copilot/eval_test.py) — seeds a minimal Triage-shaped OutputPackageRow
directly, since draft() only reads generic dict fields off the source payload.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, col, select

import core.models  # noqa: F401  (register shared tables)
import pytest
from core.common.dtos import Ctx
from core.common.dtos import Decision as DecisionDTO
from core.common.dtos import Draft
from core.common.dtos import OutputPackage as OutputPackageDTO
from core.common.enums import DecisionOutcome, Role, Vertical
from core.models import Tenant
from core.review_queue import DefaultReviewQueueService
from verticals.mga.broker_copilot.service import WORKFLOW, BrokerCopilotService
from verticals.mga.models import MgaBrokerCommResult


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


async def _seed_triage_output(session: AsyncSession, ctx: Ctx, submission_id: str) -> None:
    """Minimal Triage-shaped OutputPackage — draft() only reads generic dict
    fields off `detail`/`row` (narrative, missingInfo, consistency, changes,
    broker, insured), all tolerated as absent via .get(...) chains."""
    out_dto = OutputPackageDTO(
        submission_id=submission_id,
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=90, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={
            "detail": {"narrative": "Clean submission, appetite match.", "broker": {
                "name": "Jordan Blake", "agency": "RT Specialty", "email": "jordan@rt.example",
            }},
            "row": {"insured": "Acme LLC"},
        },
    )
    await DefaultReviewQueueService().enqueue(session, ctx, out_dto, "submission-triage")


async def test_draft_is_idempotent_for_the_same_source_decision(mga_ctx, mem_session) -> None:
    await _seed_triage_output(mem_session, mga_ctx, "sub-1")
    svc = BrokerCopilotService()

    first = await svc.draft(mem_session, mga_ctx, "submission-triage", "sub-1")
    second = await svc.draft(mem_session, mga_ctx, "submission-triage", "sub-1")
    assert first.id == second.id

    drafts = await svc.list_drafts(mem_session, mga_ctx)
    assert len(drafts) == 1
    results = (await mem_session.execute(select(MgaBrokerCommResult))).scalars().all()
    assert len(results) == 1


async def test_draft_creates_distinct_entries_for_distinct_sources(mga_ctx, mem_session) -> None:
    """The idempotency guard must not over-match — two genuinely different source
    decisions still produce two distinct drafts."""
    await _seed_triage_output(mem_session, mga_ctx, "sub-1")
    await _seed_triage_output(mem_session, mga_ctx, "sub-2")
    svc = BrokerCopilotService()

    first = await svc.draft(mem_session, mga_ctx, "submission-triage", "sub-1")
    second = await svc.draft(mem_session, mga_ctx, "submission-triage", "sub-2")
    assert first.id != second.id

    drafts = await svc.list_drafts(mem_session, mga_ctx)
    assert len(drafts) == 2


async def test_draft_is_idempotent_for_the_same_fixture_trigger(mga_ctx, mem_session) -> None:
    """Same guarantee for the fixture-fallback path (_load_source creates a fresh
    Submission row per call when no real source decision is persisted yet) — a
    repeated draft() call for the same unresolved trigger id must still reuse the
    existing draft rather than creating a second fixture Submission + draft."""
    svc = BrokerCopilotService()
    first = await svc.draft(mem_session, mga_ctx, "submission-triage", "SUB-2210")
    second = await svc.draft(mem_session, mga_ctx, "submission-triage", "SUB-2210")
    assert first.id == second.id

    drafts = await svc.list_drafts(mem_session, mga_ctx)
    assert len(drafts) == 1
    results = (await mem_session.execute(select(MgaBrokerCommResult))).scalars().all()
    assert len(results) == 1
