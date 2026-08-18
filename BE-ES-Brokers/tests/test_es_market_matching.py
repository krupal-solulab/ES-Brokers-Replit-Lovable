"""E&S Market Matching eval test — proves the pipeline against the REAL
Workflow_10 dataset (originally ``Data sets/Workflow_10/test_dataset``,
copied to ``TEST_DATA_ROOT/Workflow_10/test_dataset`` per DATA_AND_FIXTURES.md;
see that folder's Validation_Rules_Test_Dataset.md for the expected-outcome
spec this test asserts against, including one documented deviation from the
dataset's own interpretation guide).

Pytest-discovered here (not under ``src/verticals/es/...``) because this
project's ``pyproject.toml`` sets ``testpaths = ["tests"]`` — see
``verticals/es/workflows/market_matching/eval_test.py`` for that note.
"""

from __future__ import annotations

import pytest

from fixtures.loader import dataset_dir as _bundled_dataset_dir
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from sqlmodel import col, select

import core.models  # noqa: F401  (registers tables)
from core.audit import DefaultAuditService
from core.common.dtos import AuditEntry, Ctx, RawBundle, RawDocument, WorkflowInput
from core.common.enums import DecisionOutcome, DocumentKind, ReviewStatus, Role, Vertical
from core.config import get_settings
from core.documents import LocalDocumentStore
from core.extraction import DefaultExtractionService
from core.ingestion import MockConnectorService
from core.llm import build_llm_service
from core.models import ReviewItem as ReviewItemRow
from core.models import Tenant
from core.review_queue import DefaultReviewQueueService
from core.rules_engine import DefaultRulesEngine
from verticals.es.workflows.market_matching.router import RunRequest, run_market_matching
from verticals.es.workflows.market_matching.service import (
    DEFAULT_WORKFLOW_N,
    MarketMatchingPipeline,
)

pytestmark = pytest.mark.skipif(
    _bundled_dataset_dir(10) is None,
    reason="Workflow_10 fixture dataset not found (TEST_DATA_ROOT or bundled Data sets)",
)


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
def es_ctx() -> Ctx:
    return Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u-jr", role=Role.JUNIOR)


def _pipeline(session: AsyncSession) -> MarketMatchingPipeline:
    return MarketMatchingPipeline(
        session=session,
        connector=MockConnectorService(workflow_n=DEFAULT_WORKFLOW_N),
        extraction=DefaultExtractionService(),
        rules_engine=DefaultRulesEngine(),
        llm=build_llm_service(),
        documents=LocalDocumentStore(),
        workflow_n=DEFAULT_WORKFLOW_N,
    )


async def _decide_for(session: AsyncSession, ctx: Ctx, submission_ref: str):
    pipeline = _pipeline(session)
    inp = WorkflowInput(submission_id=submission_ref, source_ref=submission_ref)
    raw = await pipeline.ingest(ctx, inp)
    model = await pipeline.extract(ctx, raw)
    decision = await pipeline.decide(ctx, model)
    return model, decision


def _match_ids(decision) -> list[str]:
    return [m["carrier_id"] for m in decision.details["matches"]]


def _excluded_ids(decision) -> set[str]:
    return {e["carrier_id"] for e in decision.details["excluded"]}


async def test_ingest_and_extract_real_fixtures(es_session, es_ctx) -> None:
    pipeline = _pipeline(es_session)
    inp = WorkflowInput(submission_id="submission_01", source_ref="submission_01")
    raw = await pipeline.ingest(es_ctx, inp)
    # acord, loss_run, financial_statement, email — MockConnectorService.to_raw_bundle()
    # includes the cover email in `.documents` too (unlike get_attachments(), which
    # filters it out); it's also set separately as `raw.email_body`.
    assert len(raw.documents) == 4

    model = await pipeline.extract(es_ctx, raw)
    extracted = [f for f in model.fields if not f.name.startswith("documents.")]
    assert extracted and all(f.citation is not None for f in extracted)  # every value cited
    assert any(f.name == "acord.class_code" for f in model.fields)


async def test_submission_01_completeness_ranks_not_excludes(es_session, es_ctx) -> None:
    """MM-06: a carrier missing loss-run history is ranked lower with a flag,
    NEVER hard-excluded — this is the specific mistake the interpretation guide
    calls out as the most common wrong implementation."""
    _, decision = await _decide_for(es_session, es_ctx, "submission_01")
    assert decision.outcome is DecisionOutcome.PROCEED

    ids = _match_ids(decision)
    assert ids[0] == "CAR-03"  # Ironclad #1 — its 3yr requirement is already fully met
    assert "CAR-01" in ids  # Meridian NOT hard-excluded despite the loss-run gap
    assert "CAR-02" in ids  # Palmetto NOT hard-excluded despite the loss-run gap

    by_id = {m["carrier_id"]: m for m in decision.details["matches"]}
    assert by_id["CAR-01"]["missing"], "Meridian should carry a missing-loss-history flag"
    assert by_id["CAR-02"]["missing"], "Palmetto should carry a missing-loss-history flag"
    assert not by_id["CAR-03"]["missing"], "Ironclad's requirements are already fully met"


async def test_submission_02_habitational_class_exclusion(es_session, es_ctx) -> None:
    _, decision = await _decide_for(es_session, es_ctx, "submission_02")
    assert _match_ids(decision) == ["CAR-04"]  # Coastal Mutual only
    assert {"CAR-01", "CAR-02", "CAR-03", "CAR-05", "CAR-06"} <= _excluded_ids(decision)


async def test_submission_03_premium_floor(es_session, es_ctx) -> None:
    _, decision = await _decide_for(es_session, es_ctx, "submission_03")
    assert _match_ids(decision) == ["CAR-05"]  # Apex Excess Lines only


async def test_submission_04_premium_ceiling(es_session, es_ctx) -> None:
    _, decision = await _decide_for(es_session, es_ctx, "submission_04")
    ids = _match_ids(decision)
    assert ids[0] == "CAR-06"  # Vantage — the clean, top-ranked match
    assert "CAR-01" not in ids and "CAR-02" not in ids and "CAR-04" not in ids
    # Documented deviation from the interpretation guide's summary-table prose:
    # per the ACTUAL carrier_03_ironclad.json (trucking accepted, premium in-band)
    # there is no hard-exclusion basis for Ironclad here — MM-05 severity is a
    # soft factor for this (non-roofing) class, so it appears, score-penalized,
    # rather than excluded. See Validation_Rules_Test_Dataset.md.
    if "CAR-03" in ids:
        by_id = {m["carrier_id"]: m for m in decision.details["matches"]}
        assert by_id["CAR-03"]["score"] < by_id["CAR-06"]["score"]


async def test_submission_05_roofing_scope_and_severity(es_session, es_ctx) -> None:
    """Tests both class-scope nuance (steep vs. low-slope) and the severity
    ceiling being HARD for this (roofing) class specifically."""
    _, decision = await _decide_for(es_session, es_ctx, "submission_05")
    assert _match_ids(decision) == ["CAR-03"]  # Ironclad only
    excluded = _excluded_ids(decision)
    assert {"CAR-01", "CAR-04"} <= excluded  # Meridian, Coastal Mutual — class
    assert "CAR-02" in excluded  # Palmetto — accepts low-slope only, not steep


async def test_submission_06_zero_match_and_diligent_search(es_session, es_ctx) -> None:
    """The single most important failure mode per the interpretation guide:
    resist forcing a low-confidence match when no real fit exists."""
    _, decision = await _decide_for(es_session, es_ctx, "submission_06")
    assert decision.outcome is DecisionOutcome.DECLINE
    assert decision.details["matches"] == []
    assert len(decision.details["excluded"]) == 6  # every carrier, class-excluded (cannabis)
    # MM-07 fires regardless of the zero-match outcome.
    assert decision.details["diligent_search"]["required"] is True


async def test_missing_acord_yields_request_info(es_session, es_ctx) -> None:
    """Synthetic case — this dataset's 6 real submissions all include an ACORD,
    so this constructs a bundle without one to prove the REQUEST_INFO path:
    no class code / premium means no carrier matching can even be attempted,
    independent of any specific carrier's appetite."""
    pipeline = _pipeline(es_session)
    raw = RawBundle(
        submission_id="synthetic-no-acord",
        documents=[
            RawDocument(
                kind=DocumentKind.LOSS_RUN, filename="loss_run.txt",
                content="Named Insured: Test Co\n",
            )
        ],
    )
    model = await pipeline.extract(es_ctx, raw)
    decision = await pipeline.decide(es_ctx, model)
    assert decision.outcome is DecisionOutcome.REQUEST_INFO


async def test_score_components_and_outcome_codes(es_session, es_ctx) -> None:
    """Regression for the deterministic breakdown + explicit outcome signal:
    each ranked match carries the engine's five score components + weights, and
    the decision records MATCHES_FOUND / NO_MATCH / REQUEST_INFO explicitly."""
    _, decision = await _decide_for(es_session, es_ctx, "submission_01")
    assert decision.details["outcome"] == "MATCHES_FOUND"
    top = decision.details["matches"][0]
    assert set(top["score_components"]) == {
        "class_fit_specificity", "completeness_score", "historical_hit_rate",
        "appetite_confidence_weight", "severity_margin",
    }
    assert top["score_weights"] and abs(sum(top["score_weights"].values()) - 1.0) < 1e-9

    _, no_match = await _decide_for(es_session, es_ctx, "submission_06")
    assert no_match.details["outcome"] == "NO_MATCH"

    # No readable class code / premium (but panel evaluable) → REQUEST_INFO,
    # not a false "every carrier excluded" NO_MATCH.
    pipeline = _pipeline(es_session)
    raw = RawBundle(
        submission_id="synthetic-blank-acord",
        documents=[
            RawDocument(
                kind=DocumentKind.ACORD, filename="acord.txt",
                content="Named Insured: Test Co\n",
            )
        ],
    )
    model = await pipeline.extract(es_ctx, raw)
    decision = await pipeline.decide(es_ctx, model)
    assert decision.details.get("outcome") == "REQUEST_INFO"


async def test_full_pipeline_draft_review_and_audit(es_session, es_ctx) -> None:
    """ingest -> extract -> decide -> draft -> package -> review queue -> audit,
    end to end, for a real submission with an actual top match."""
    pipeline = _pipeline(es_session)
    output = await pipeline.run(
        es_ctx, WorkflowInput(submission_id="submission_01", source_ref="submission_01")
    )
    assert output.decision.outcome is DecisionOutcome.PROCEED
    assert output.draft is not None and output.draft.text
    assert output.payload["matches"][0]["carrier_id"] == "CAR-03"

    rq = DefaultReviewQueueService()
    item = await rq.enqueue(es_session, es_ctx, output, "market_matching")
    assert item.status is ReviewStatus.PENDING

    audit = DefaultAuditService()
    await audit.record(
        es_session, es_ctx,
        AuditEntry(
            actor="ai", who="system", what=f"decision={output.decision.outcome.value}",
            workflow="market_matching", tenant_id=es_ctx.tenant_id, vertical=es_ctx.vertical,
        ),
    )
    entries = await audit.query(es_session, es_ctx, {"workflow": "market_matching"})
    assert len(entries) == 1
    assert entries[0].actor == "ai"


async def test_zero_match_seeds_diligent_search_stub(es_session, es_ctx) -> None:
    """MM-07 -> Diligent Search (Phase 2 connectivity): a real zero-match
    result whose diligent_search flag is required must seed a real, linked
    Diligent Search review item stub — additive, via /run's router-level
    hook, not a fake determination. Re-running the same submission must
    never create a second stub."""
    await run_market_matching(RunRequest(submission_ref="submission_06"), es_ctx, es_session)

    ds_items = (
        await es_session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.tenant_id) == es_ctx.tenant_id,
                col(ReviewItemRow.workflow) == "diligent_search",
            )
        )
    ).scalars().all()
    assert len(ds_items) == 1

    await run_market_matching(RunRequest(submission_ref="submission_06"), es_ctx, es_session)
    ds_items_again = (
        await es_session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.tenant_id) == es_ctx.tenant_id,
                col(ReviewItemRow.workflow) == "diligent_search",
            )
        )
    ).scalars().all()
    assert len(ds_items_again) == 1


class _FakeLiveConnector:
    """Stands in for LiveNangoConnectorService in the /live-inbox router test —
    the connector's own real behavior is proven separately in
    tests/test_live_nango_connector.py; this only proves the router wires it up
    and translates ConnectorNotConnectedError into a 428."""

    def __init__(self, *, messages=None, raise_not_connected=False) -> None:
        self._messages = messages or []
        self._raise_not_connected = raise_not_connected

    async def fetch_inbox(self, ctx, since_cursor=None):
        if self._raise_not_connected:
            from core.ingestion import ConnectorNotConnectedError

            raise ConnectorNotConnectedError("google-mail")
        return self._messages


async def test_list_live_inbox_returns_real_messages(monkeypatch, es_ctx, es_session) -> None:
    from core.ingestion import EmailMessage
    from verticals.es.workflows.market_matching import router as mm_router

    monkeypatch.setattr(
        mm_router,
        "build_connector_service",
        lambda **kwargs: _FakeLiveConnector(
            messages=[EmailMessage(id="msg-1", submission_ref="msg-1", subject="Real Submission", body="")]
        ),
    )
    result = await mm_router.list_live_inbox(es_ctx, es_session)
    assert len(result) == 1
    assert result[0].id == "msg-1"
    assert result[0].subject == "Real Submission"


async def test_list_live_inbox_428_when_gmail_not_connected(monkeypatch, es_ctx, es_session) -> None:
    from fastapi import HTTPException

    from verticals.es.workflows.market_matching import router as mm_router

    monkeypatch.setattr(
        mm_router,
        "build_connector_service",
        lambda **kwargs: _FakeLiveConnector(raise_not_connected=True),
    )
    with pytest.raises(HTTPException) as exc_info:
        await mm_router.list_live_inbox(es_ctx, es_session)
    assert exc_info.value.status_code == 428


# ---------------------------------------------------------------------------
# QA-fix regression tests (fixes #3/#4/#5): grounded recommendation, real Send
# handoff to Package Assembly, exclusion override, and removed endpoints.
# ---------------------------------------------------------------------------

from fastapi import HTTPException  # noqa: E402

from verticals.es.workflows.market_matching.router import (  # noqa: E402
    OverrideExclusionRequest,
    override_exclusion,
    router as _mm_router_obj,
)
from verticals.es.workflows.package_assembly.router import (  # noqa: E402
    RunFromMarketMatchingRequest,
    run_package_assembly_from_market_matching,
)


@pytest.fixture
def es_senior_ctx() -> Ctx:
    return Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u-sr", role=Role.SENIOR)


def _grounded_recommendation(payload: dict) -> dict[str, list[str]]:
    """Mirror of the FE's deterministic recommendation builder — lines composed
    ONLY from recorded engine fields; used to assert the grounding contract."""
    approach, hold = [], []
    for m in payload["matches"]:
        if m.get("overridden"):
            continue
        if m["missing"]:
            hold.append(f"Hold {m['carrier_name']} pending: {'; '.join(m['missing'])}")
            continue
        comps = m.get("score_components") or {}
        drivers = [k for k, _ in sorted(comps.items(), key=lambda kv: -kv[1])[:2]]
        approach.append(f"Approach {m['carrier_name']} — {', '.join(drivers)}")
    excluded = [f"{e['carrier_name']} — {e['rule']}: {e['reason']}" for e in payload["excluded"]]
    return {"approach": approach, "hold": hold, "excluded": excluded}


async def test_recommendation_is_grounded_in_engine_output(es_ctx, es_session) -> None:
    """Fix #3: every carrier/reason in the recommendation maps to a real engine
    field; nothing invented, and the numeric composite score is never restated."""
    item = await run_market_matching(RunRequest(submission_ref="submission_01"), es_ctx, es_session)
    payload = item.payload.model_dump()
    rec = _grounded_recommendation(payload)

    engine_names = {m["carrier_name"] for m in payload["matches"]} | {
        e["carrier_name"] for e in payload["excluded"]
    }
    all_lines = rec["approach"] + rec["hold"] + rec["excluded"]
    assert all_lines, "PROCEED case must produce recommendation lines"
    for line in all_lines:
        assert any(name in line for name in engine_names), f"ungrounded carrier in: {line}"

    # Reasons map to real engine fields only.
    component_keys = set()
    for m in payload["matches"]:
        component_keys |= set((m.get("score_components") or {}).keys())
    for line in rec["approach"]:
        m = next(x for x in payload["matches"] if x["carrier_name"] in line)
        for token in line.split(" — ", 1)[1].split(", "):
            assert token in component_keys, f"driver '{token}' is not an engine component"
        # The composite score itself is never restated in the text.
        assert str(m["score"]) not in line
    for line in rec["hold"]:
        m = next(x for x in payload["matches"] if x["carrier_name"] in line)
        for item_missing in m["missing"]:
            assert item_missing in line
    for line, e in zip(rec["excluded"], payload["excluded"]):
        assert e["rule"] in line and e["reason"] in line


async def test_recommendation_zero_match_never_picks_best_available(es_ctx, es_session) -> None:
    """Fix #3 (zero-match): DECLINE means an explicit no-carrier statement —
    the recommendation must have no carrier to approach or hold, ever."""
    item = await run_market_matching(RunRequest(submission_ref="submission_06"), es_ctx, es_session)
    payload = item.payload.model_dump()
    assert payload["outcome"] == "NO_MATCH"
    rec = _grounded_recommendation(payload)
    assert rec["approach"] == [] and rec["hold"] == []
    assert len(rec["excluded"]) == 6  # every carrier, with its recorded rule+reason


async def test_send_hands_off_exactly_selected_carriers(es_ctx, es_senior_ctx, es_session) -> None:
    """Fix #4 (FR-13): senior Send creates Package Assembly inputs for EXACTLY
    the selected carriers, writes one human audit row, rejects an empty
    selection, and sends no outbound message to any carrier."""
    item = await run_market_matching(RunRequest(submission_ref="submission_01"), es_ctx, es_session)
    surviving = [m["carrier_id"] for m in item.payload.model_dump()["matches"]][:2]
    assert len(surviving) == 2

    created = await run_package_assembly_from_market_matching(
        RunFromMarketMatchingRequest(
            market_matching_review_item_id=item.id, carrier_ids=surviving
        ),
        es_senior_ctx, es_session,
    )
    assert sorted(i.carrier_id for i in created) == sorted(surviving)  # exactly, no more/fewer

    audit_rows = await DefaultAuditService().query(
        es_session, es_senior_ctx, {"workflow": "package_assembly"}
    )
    handoff = [r for r in audit_rows if r.actor == "human" and "handoff" in r.what]
    assert len(handoff) == 1
    assert handoff[0].who == "u-sr"
    assert handoff[0].detail["submission_id"] == item.submission_id
    assert handoff[0].detail["carrier_ids"] == surviving

    # No outbound message to a carrier: nothing left the review queue as sent,
    # and no audit row records an email being sent.
    sent_items = (
        await es_session.execute(
            select(ReviewItemRow).where(col(ReviewItemRow.status) == ReviewStatus.SENT)
        )
    ).scalars().all()
    assert sent_items == []
    assert not any("email" in r.what.lower() for r in audit_rows)

    # Empty selection rejected.
    with pytest.raises(HTTPException) as exc:
        await run_package_assembly_from_market_matching(
            RunFromMarketMatchingRequest(
                market_matching_review_item_id=item.id, carrier_ids=[]
            ),
            es_senior_ctx, es_session,
        )
    assert exc.value.status_code == 422

    # Junior cannot send at all (senior/admin only, server-side).
    with pytest.raises(HTTPException) as exc:
        await run_package_assembly_from_market_matching(
            RunFromMarketMatchingRequest(
                market_matching_review_item_id=item.id, carrier_ids=surviving
            ),
            es_ctx, es_session,
        )
    assert exc.value.status_code == 403


async def test_override_moves_excluded_carrier_and_is_audited(
    es_ctx, es_senior_ctx, es_session
) -> None:
    """Fix #5: junior override -> 403; senior without reason -> 422; with a
    reason the carrier moves into the shortlist (no engine score), an audit row
    records carrier/rule/reason/user, and the carrier is now sendable."""
    item = await run_market_matching(RunRequest(submission_ref="submission_02"), es_ctx, es_session)
    excluded = item.payload.model_dump()["excluded"]
    assert excluded, "submission_02 must have hard-excluded carriers"
    target = excluded[0]

    with pytest.raises(HTTPException) as exc:
        await override_exclusion(
            item.id, OverrideExclusionRequest(carrier_id=target["carrier_id"], reason="x"),
            es_ctx, es_session,
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await override_exclusion(
            item.id, OverrideExclusionRequest(carrier_id=target["carrier_id"], reason="   "),
            es_senior_ctx, es_session,
        )
    assert exc.value.status_code == 422

    updated = await override_exclusion(
        item.id,
        OverrideExclusionRequest(carrier_id=target["carrier_id"], reason="manager approved"),
        es_senior_ctx, es_session,
    )
    moved = [m for m in updated.payload.model_dump()["matches"] if m["carrier_id"] == target["carrier_id"]]
    assert len(moved) == 1
    assert moved[0]["overridden"] is True
    assert moved[0]["score"] == 0.0  # no invented engine score
    assert moved[0]["override_rule"] == target["rule"]
    assert target["carrier_id"] not in {e["carrier_id"] for e in updated.payload.model_dump()["excluded"]}

    rows = await DefaultAuditService().query(
        es_session, es_senior_ctx, {"workflow": "market_matching"}
    )
    ov = [r for r in rows if r.actor == "human" and "override" in r.what]
    assert len(ov) == 1
    assert ov[0].who == "u-sr"
    assert ov[0].detail["carrier_id"] == target["carrier_id"]
    assert ov[0].detail["rule_overridden"] == target["rule"]
    assert ov[0].detail["reason"] == "manager approved"

    # The overridden carrier is now selectable for Send.
    created = await run_package_assembly_from_market_matching(
        RunFromMarketMatchingRequest(
            market_matching_review_item_id=item.id, carrier_ids=[target["carrier_id"]]
        ),
        es_senior_ctx, es_session,
    )
    assert [i.carrier_id for i in created] == [target["carrier_id"]]


def test_send_and_issue_endpoints_removed_from_market_matching() -> None:
    """Fix #5 (+#4): neither a bare /send status flip nor an /issue endpoint
    exists on the Market Matching router anymore."""
    paths = {r.path for r in _mm_router_obj.routes}
    assert not any(p.endswith("/send") for p in paths)
    assert not any(p.endswith("/issue") for p in paths)
