"""Proves the Calendar-export fallback (docs/CONNECTORS_NANGO.md): connector-level
create_event against a mocked Nango Calendar proxy (httpx.MockTransport, no real
network), and each of the 3 scoped workflows' (Bind Issuance, Bordereau Reporting,
Renewal Management) per-item add-to-calendar method — a manual, per-item action
(per-obligation for Bind Issuance, since one bind can have several) that
creates/updates one all-day event. Unlike Sheets/Drive, Calendar is NOT a
page-level bulk action — each item/obligation has its own trigger. act() has no
Calendar side effect anywhere.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import core.models  # noqa: F401  (registers tables)
from core.common.dtos import Ctx
from core.common.dtos import Decision as DecisionDTO
from core.common.dtos import Draft
from core.common.dtos import OutputPackage as OutputPackageDTO
from core.common.enums import DecisionOutcome, Role, Vertical
from core.config import get_settings
import re

from core.ingestion.connectors import (
    ConnectorNotConnectedError,
    LiveNangoConnectorService,
    MockConnectorService,
    _calendar_safe_event_id,
)
from core.ingestion.writeback import try_create_event
from core.integrations.repository import upsert_connection
from core.models import Tenant
from verticals.mga.bind_issuance.schema import (
    BindDetail,
    DownstreamTriggersOut,
    IssuanceReconciliationOut,
    PostBindObligationOut,
    ActivityEntry as BindActivityEntry,
    WriteBackOut,
)
from verticals.mga.bind_issuance.service import WORKFLOW as BIND_WORKFLOW
from verticals.mga.bind_issuance.service import BindIssuanceService
from verticals.mga.bordereau_reporting.schema import (
    BordereauDetail,
    CompletenessCheckOut,
    DataCurrencyCheckOut,
    FormatComplianceCheckOut,
    ReconciliationCheckOut,
)
from verticals.mga.bordereau_reporting.service import WORKFLOW as BORDEREAU_WORKFLOW
from verticals.mga.bordereau_reporting.service import BordereauService
from verticals.mga.renewal_management.schema import (
    RenewalBroker,
    RenewalDetail,
    RenewalRow,
    RenewalTiming,
)
from verticals.mga.renewal_management.service import WORKFLOW as RENEWAL_WORKFLOW
from verticals.mga.renewal_management.service import RenewalService


@pytest.fixture
async def mga_session() -> AsyncGenerator[AsyncSession, None]:
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
    return Ctx(tenant_id="demo-mga", vertical=Vertical.MGA, user_id="u-sr", role=Role.SENIOR)


@pytest.fixture(autouse=True)
def _force_mock_connectors_mode(monkeypatch):
    """The real .env sets CONNECTORS_MODE=live for this deployment — force "mock"
    for every test in this file so calendar export's connector call never attempts
    a real Nango request via build_connector_service."""
    monkeypatch.setenv("CONNECTORS_MODE", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _calendar_handler(request: httpx.Request) -> httpx.Response:
    """Exact-path-matched, per the lesson from Sheets: a loose match is exactly
    what let a wrong path ship to production undetected. GET-then-upsert: a GET
    on a not-yet-created event id 404s (insert path); once "created" (tracked in
    module-level state for this handler's lifetime), a later GET 200s (update
    path)."""
    created: set[str] = _calendar_handler.created  # type: ignore[attr-defined]
    path = request.url.path
    prefix = "/proxy/calendar/v3/calendars/primary/events"
    if path == prefix and request.method == "POST":
        body = json.loads(request.content)
        assert "id" in body
        assert body["start"]["date"]
        assert body["end"]["date"]
        created.add(body["id"])
        return httpx.Response(200, json={"id": body["id"]})
    if path.startswith(prefix + "/"):
        event_id = path[len(prefix) + 1 :]
        if request.method == "GET":
            if event_id in created:
                return httpx.Response(200, json={"id": event_id})
            return httpx.Response(404, json={"error": "not found"})
        if request.method == "PATCH":
            body = json.loads(request.content)
            assert body["start"]["date"]
            return httpx.Response(200, json={"id": event_id})
    return httpx.Response(404, json={"error": f"unhandled {request.method} {path}"})


_calendar_handler.created = set()  # type: ignore[attr-defined]


@pytest.fixture
def mocked_calendar_transport(monkeypatch):
    _calendar_handler.created = set()  # type: ignore[attr-defined]
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_calendar_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def _connected_calendar_service(mga_ctx, mga_session) -> LiveNangoConnectorService:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-calendar",
        nango_connection_id="conn-cal-1", status="connected",
    )
    return LiveNangoConnectorService(get_settings(), mga_session)


# ── _calendar_safe_event_id: Google's events.insert only accepts base32hex
#    (lowercase a-v, digits 0-9), 5-1024 chars — this is the exact constraint a
#    real "bind-issuance-{uuid}-obligation-0"-shaped id violates (hyphens, and
#    letters outside a-v), which is what produced the live 400 this covers ──


def test_calendar_safe_event_id_matches_google_charset() -> None:
    safe = _calendar_safe_event_id("bind-issuance-ef6a6fcd-d1ea-4ece-843d-obligation-0")
    assert re.fullmatch(r"[0-9a-v]{5,1024}", safe)


def test_calendar_safe_event_id_is_deterministic() -> None:
    raw = "renewal-management-sub-4"
    assert _calendar_safe_event_id(raw) == _calendar_safe_event_id(raw)


def test_calendar_safe_event_id_differs_for_different_input() -> None:
    assert _calendar_safe_event_id("a") != _calendar_safe_event_id("b")


# ── connector-level: LiveNangoConnectorService ──


async def test_create_event_not_connected_raises(mga_ctx, mga_session) -> None:
    service = LiveNangoConnectorService(get_settings(), mga_session)
    with pytest.raises(ConnectorNotConnectedError):
        await service.create_event(
            mga_ctx, "evt-1", summary="s", description="d",
            start_date="2027-01-01", end_date="2027-01-01",
        )


async def test_create_event_inserts_when_not_yet_existing(
    mga_ctx, mga_session, mocked_calendar_transport,
) -> None:
    service = await _connected_calendar_service(mga_ctx, mga_session)
    event_id = await service.create_event(
        mga_ctx, "evt-new", summary="Renewal due", description="d",
        start_date="2027-06-01", end_date="2027-06-01",
    )
    # The raw caller id ("evt-new") isn't itself a valid Google event id (Google's
    # events.insert only accepts base32hex — lowercase a-v and digits 0-9, no
    # hyphens) — create_event maps it deterministically via _calendar_safe_event_id,
    # so the returned id is that mapped id, not the raw string.
    assert event_id
    assert event_id != "evt-new"


async def test_create_event_updates_on_repeat_call(
    mga_ctx, mga_session, mocked_calendar_transport,
) -> None:
    """A repeat call with the SAME event_id must PATCH the existing event, not
    insert a duplicate — the GET-then-upsert pattern, since Google's own docs say
    duplicate-id collisions aren't reliably caught at insert time. The SAME raw id
    must map to the SAME safe id both times, or the GET-then-upsert idempotency
    check would never find the first call's event."""
    service = await _connected_calendar_service(mga_ctx, mga_session)
    first_id = await service.create_event(
        mga_ctx, "evt-repeat", summary="first", description="d",
        start_date="2027-06-01", end_date="2027-06-01",
    )
    second_id = await service.create_event(
        mga_ctx, "evt-repeat", summary="updated", description="d",
        start_date="2027-06-02", end_date="2027-06-02",
    )
    assert first_id == second_id


# ── connector-level: MockConnectorService ──


async def test_mock_create_event_records_in_memory() -> None:
    ctx = Ctx(tenant_id="demo-mga", vertical=Vertical.MGA, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    event_id = await service.create_event(
        ctx, "evt-1", summary="s", description="d",
        start_date="2027-01-01", end_date="2027-01-01",
    )
    assert event_id == "evt-1"
    assert service._events["evt-1"]["summary"] == "s"


async def test_mock_create_event_overwrites_on_repeat_call() -> None:
    ctx = Ctx(tenant_id="demo-mga", vertical=Vertical.MGA, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    await service.create_event(
        ctx, "evt-1", summary="first", description="d",
        start_date="2027-01-01", end_date="2027-01-01",
    )
    await service.create_event(
        ctx, "evt-1", summary="second", description="d",
        start_date="2027-01-02", end_date="2027-01-02",
    )
    assert service._events["evt-1"]["summary"] == "second"
    assert len(service._events) == 1


# ── try_create_event helper: never raises, reports status ──


async def test_try_create_event_skips_when_not_connected(mga_ctx, mga_session) -> None:
    connector = LiveNangoConnectorService(get_settings(), mga_session)
    status = await try_create_event(
        connector, mga_ctx, "evt-1", summary="s", description="d",
        start_date="2027-01-01", end_date="2027-01-01",
    )
    assert status == "skipped-not-connected"


async def test_try_create_event_ok_when_connected(
    mga_ctx, mga_session, mocked_calendar_transport,
) -> None:
    connector = await _connected_calendar_service(mga_ctx, mga_session)
    status = await try_create_event(
        connector, mga_ctx, "evt-1", summary="s", description="d",
        start_date="2027-01-01", end_date="2027-01-01",
    )
    assert status == "ok"


# ── workflow add_to_calendar: per-item, per-obligation; act() has no Calendar
#    side effect ──


async def test_bind_issuance_act_no_longer_touches_calendar(mga_ctx, mga_session) -> None:
    service = BindIssuanceService()
    detail = BindDetail(
        bindId="BND-1", submissionId="sub-1", namedInsured="Acme LLC",
        worksheetReference=None, stalenessCheck=None, preBindSubjectivities=[],
        authorityReconfirmation=None, bindOrderStatus="READY",
        pasWriteBack=WriteBackOut(logged=True, bordereauSchemaValidated=True),
        issuanceReconciliation=IssuanceReconciliationOut(status="NOT_YET_ISSUED", discrepancyDetail=[]),
        postBindObligations=[
            PostBindObligationOut(description="File proof of coverage within 30 days",
                                  dueDate="+30d", status="open", reminderDaysBefore=[15, 5]),
        ],
        downstreamTriggersFired=DownstreamTriggersOut(bindConfirmation=False, policyDelivered=False),
        rationale="ok", activity=[BindActivityEntry(at="2027-01-01T00:00:00+00:00", who="system (AI)",
                                                     what="Bind order evaluated -> READY")],
    )
    out_dto = OutputPackageDTO(
        submission_id="sub-1",
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={"detail": detail.model_dump(by_alias=True)},
    )
    await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, BIND_WORKFLOW)

    result = await service.act(mga_session, mga_ctx, "sub-1", "approve")
    assert result["status"] == "approved"


async def test_bind_issuance_add_obligation_to_calendar_skips_when_not_connected(
    mga_ctx, mga_session, monkeypatch,
) -> None:
    """MockConnectorService always "succeeds" (no connection concept), so this
    forces CONNECTORS_MODE=live with no seeded Connection row — the real path a
    genuinely unconnected tenant hits — to prove the guard works end to end."""
    monkeypatch.setenv("CONNECTORS_MODE", "live")
    get_settings.cache_clear()
    service = BindIssuanceService()
    detail = BindDetail(
        bindId="BND-1", submissionId="sub-1", namedInsured="Acme LLC",
        worksheetReference=None, stalenessCheck=None, preBindSubjectivities=[],
        authorityReconfirmation=None, bindOrderStatus="READY",
        pasWriteBack=WriteBackOut(logged=True, bordereauSchemaValidated=True),
        issuanceReconciliation=IssuanceReconciliationOut(status="NOT_YET_ISSUED", discrepancyDetail=[]),
        postBindObligations=[
            PostBindObligationOut(description="File proof of coverage within 30 days",
                                  dueDate="+30d", status="open", reminderDaysBefore=[15, 5]),
        ],
        downstreamTriggersFired=DownstreamTriggersOut(bindConfirmation=False, policyDelivered=False),
        rationale="ok", activity=[BindActivityEntry(at="2027-01-01T00:00:00+00:00", who="system (AI)",
                                                     what="Bind order evaluated -> READY")],
    )
    out_dto = OutputPackageDTO(
        submission_id="sub-1",
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={"detail": detail.model_dump(by_alias=True)},
    )
    await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, BIND_WORKFLOW)

    status = await service.add_obligation_to_calendar(mga_session, mga_ctx, "sub-1", 0)
    assert status == "skipped-not-connected"
    get_settings.cache_clear()


async def test_bind_issuance_add_obligation_to_calendar_rejects_out_of_range_index(
    mga_ctx, mga_session,
) -> None:
    service = BindIssuanceService()
    detail = BindDetail(
        bindId="BND-1", submissionId="sub-1", namedInsured="Acme LLC",
        worksheetReference=None, stalenessCheck=None, preBindSubjectivities=[],
        authorityReconfirmation=None, bindOrderStatus="READY",
        pasWriteBack=WriteBackOut(logged=True, bordereauSchemaValidated=True),
        issuanceReconciliation=IssuanceReconciliationOut(status="NOT_YET_ISSUED", discrepancyDetail=[]),
        postBindObligations=[
            PostBindObligationOut(description="File proof of coverage within 30 days",
                                  dueDate="+30d", status="open", reminderDaysBefore=[15, 5]),
        ],
        downstreamTriggersFired=DownstreamTriggersOut(bindConfirmation=False, policyDelivered=False),
        rationale="ok", activity=[BindActivityEntry(at="2027-01-01T00:00:00+00:00", who="system (AI)",
                                                     what="Bind order evaluated -> READY")],
    )
    out_dto = OutputPackageDTO(
        submission_id="sub-1",
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={"detail": detail.model_dump(by_alias=True)},
    )
    await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, BIND_WORKFLOW)

    with pytest.raises(ValueError):
        await service.add_obligation_to_calendar(mga_session, mga_ctx, "sub-1", 5)


async def test_bind_issuance_add_obligation_to_calendar_creates_event_for_open_obligation(
    mga_ctx, mga_session, mocked_calendar_transport,
) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-calendar",
        nango_connection_id="conn-cal-3", status="connected",
    )
    service = BindIssuanceService()
    detail = BindDetail(
        bindId="BND-1", submissionId="sub-1", namedInsured="Acme LLC",
        worksheetReference=None, stalenessCheck=None, preBindSubjectivities=[],
        authorityReconfirmation=None, bindOrderStatus="READY",
        pasWriteBack=WriteBackOut(logged=True, bordereauSchemaValidated=True),
        issuanceReconciliation=IssuanceReconciliationOut(status="NOT_YET_ISSUED", discrepancyDetail=[]),
        postBindObligations=[
            PostBindObligationOut(description="File proof of coverage within 30 days",
                                  dueDate="+30d", status="open", reminderDaysBefore=[15, 5]),
        ],
        downstreamTriggersFired=DownstreamTriggersOut(bindConfirmation=False, policyDelivered=False),
        rationale="ok", activity=[BindActivityEntry(at="2027-01-01T00:00:00+00:00", who="system (AI)",
                                                     what="Bind order evaluated -> READY")],
    )
    out_dto = OutputPackageDTO(
        submission_id="sub-1",
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={"detail": detail.model_dump(by_alias=True)},
    )
    await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, BIND_WORKFLOW)

    status = await service.add_obligation_to_calendar(mga_session, mga_ctx, "sub-1", 0)
    assert status == "ok"


async def test_bordereau_add_to_calendar_skips_unparseable_due_date(
    mga_ctx, mga_session,
) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-calendar",
        nango_connection_id="conn-cal-4", status="connected",
    )
    service = BordereauService()
    detail = BordereauDetail(
        bordereauId="BR-1", bordereauType="loss", carrierName="Acme Re",
        reportingPeriod="2027-Q1", dueDate="not-a-date",
        completenessCheck=CompletenessCheckOut(status="complete", missingTransactions=[]),
        formatComplianceCheck=FormatComplianceCheckOut(status="pass", issues=[]),
        reconciliationCheck=ReconciliationCheckOut(status="pass", discrepancyDetail=[]),
        dataCurrencyCheck=DataCurrencyCheckOut(status="current", staleItems=[]),
        timelinessCheck=None, status="complete", rationale="ok", activity=[],
    )
    out_dto = OutputPackageDTO(
        submission_id="sub-3",
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={"detail": detail.model_dump(by_alias=True)},
    )
    await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, BORDEREAU_WORKFLOW)

    status = await service.add_to_calendar(mga_session, mga_ctx, "sub-3")
    assert status == "skipped-no-due-date"


async def test_bordereau_add_to_calendar_ok_when_connected(
    mga_ctx, mga_session, mocked_calendar_transport,
) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-calendar",
        nango_connection_id="conn-cal-5", status="connected",
    )
    service = BordereauService()
    detail = BordereauDetail(
        bordereauId="BR-1", bordereauType="loss", carrierName="Acme Re",
        reportingPeriod="2027-Q1", dueDate="2027-04-15",
        completenessCheck=CompletenessCheckOut(status="complete", missingTransactions=[]),
        formatComplianceCheck=FormatComplianceCheckOut(status="pass", issues=[]),
        reconciliationCheck=ReconciliationCheckOut(status="pass", discrepancyDetail=[]),
        dataCurrencyCheck=DataCurrencyCheckOut(status="current", staleItems=[]),
        timelinessCheck=None, status="complete", rationale="ok", activity=[],
    )
    out_dto = OutputPackageDTO(
        submission_id="sub-3",
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={"detail": detail.model_dump(by_alias=True)},
    )
    await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, BORDEREAU_WORKFLOW)

    status = await service.add_to_calendar(mga_session, mga_ctx, "sub-3")
    assert status == "ok"


async def test_bordereau_add_to_calendar_raises_for_unknown_submission(
    mga_ctx, mga_session,
) -> None:
    service = BordereauService()
    with pytest.raises(KeyError):
        await service.add_to_calendar(mga_session, mga_ctx, "does-not-exist")


async def test_renewal_add_to_calendar_ok_when_connected(
    mga_ctx, mga_session, mocked_calendar_transport,
) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-calendar",
        nango_connection_id="conn-cal-6", status="connected",
    )
    service = RenewalService()
    detail = RenewalDetail(
        id="sub-4", subject="Renewal - Acme - Eff 2027-01-01", recommendation="RENEW_AS_IS",
        confidence=1.0, processing="ready", priorSource="manual_queue", rulesVersion="v1",
        rulesVersionAtBinding="v1", hardRulePassed=True, appetite=[], appetiteDrift=None,
        comparison=[], changeFlags=[], lossChanges=[],
        timing=RenewalTiming(daysToExpiration=30, lapseRisk=False, noSubmission=False),
        changes=[], narrative="ok", citations=[],
        broker=RenewalBroker(name="", agency="", tenure="", note="", email=""),
        activity=[], needsInfo=False, missingInfo=[], retention="neutral",
        priorPremium="$10,000", indicated="—", premiumChange="—", lossRatio="—",
    )
    row = RenewalRow(
        id="sub-4", subject=detail.subject, insured="Acme LLC",
        recommendation=detail.recommendation, score=None, retention=detail.retention,
        daysToExpiration=30, lapseRisk=False, status="pending", received="2027-01-01",
        priorPremium=detail.priorPremium, indicated=detail.indicated,
    )
    out_dto = OutputPackageDTO(
        submission_id="sub-4",
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={
            "detail": detail.model_dump(by_alias=True),
            "row": row.model_dump(),
            "activity": [],
        },
    )
    await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, RENEWAL_WORKFLOW)

    status = await service.add_to_calendar(mga_session, mga_ctx, "sub-4")
    assert status == "ok"


async def test_renewal_add_to_calendar_raises_for_unknown_submission(
    mga_ctx, mga_session,
) -> None:
    service = RenewalService()
    with pytest.raises(KeyError):
        await service.add_to_calendar(mga_session, mga_ctx, "does-not-exist")
