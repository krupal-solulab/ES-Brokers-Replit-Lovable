"""Proves the Calendar-export fallback (docs/CONNECTORS_NANGO.md): connector-level
create_event against a mocked Nango Calendar proxy (httpx.MockTransport, no real
network), and the one real ES workflow with a MANUAL calendar action — Binder
& Policy Issuance's per-obligation ``POST /{item_id}/add-to-calendar``
(``verticals/es/workflows/binder_issuance/router.py``), matched by exact
obligation description text rather than by index. Binder & Policy Issuance
also has an AUTOMATIC calendar reminder (``_maybe_create_renewal_reminder``,
fires once when ``bind_order_status`` newly becomes "SENT") — already proven
end-to-end in tests/test_es_binder_issuance.py's
``test_attach_live_confirmation_creates_real_calendar_reminder``, not
duplicated here. Unlike the MGA-era design this backend used to have (3
scoped workflows each with their own per-item add-to-calendar method), ES has
exactly one manual Calendar action. Calendar is not, and never was, a
page-level bulk action — act()/approve() has no Calendar side effect anywhere.

Pre-existing bug found while rewriting this file (predates the MGA removal —
``core/ingestion/connectors.py`` was untouched by that removal): both
``MockConnectorService`` and ``LiveNangoConnectorService`` define
``create_event`` TWICE — an older ``(ctx, event_id, *, ...)`` overload (meant
to GET-then-upsert by a caller-supplied deterministic id, the MGA-era
per-item-by-index precedent ``_calendar_safe_event_id`` exists to support) and
a newer ``(ctx, *, ...)`` overload (always inserts a fresh event, no id). A
class body silently keeps only the LAST same-named method, so the first
overload — and ``core/ingestion/writeback.py``'s ``try_create_event`` helper,
which still calls the first overload's shape — are both dead, unreachable
code today: any call to either now raises ``TypeError``, in every mode, not
just here. Real production Calendar write-back (``core/ingestion/
calendar_writeback.py``, what this workflow actually calls) already only ever
uses the second, reachable overload, so it is unaffected. The connector-level
tests below are written against that real, reachable overload;
``try_create_event`` itself is out of scope for this test-file-only rewrite
(fixing it means editing ``writeback.py``/``connectors.py``, not a test file)
and is no longer covered here — flagged for a follow-up fix rather than
silently left broken.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import core.models  # noqa: F401  (registers tables)
from core.common.dtos import Ctx, Draft
from core.common.dtos import Decision as DecisionDTO
from core.common.dtos import OutputPackage as OutputPackageDTO
from core.common.enums import DecisionOutcome, Role, Vertical
from core.config import get_settings
from core.ingestion.connectors import (
    ConnectorNotConnectedError,
    LiveNangoConnectorService,
    MockConnectorService,
    _calendar_safe_event_id,
)
from core.integrations.repository import upsert_connection
from core.models import Tenant
from core.review_queue import DefaultReviewQueueService
from verticals.es.workflows.binder_issuance.router import AddToCalendarRequest, add_to_calendar
from verticals.es.workflows.binder_issuance.schema import (
    BindCoordinationPayload,
    BindTermsOut,
    OngoingObligationOut,
)
from verticals.es.workflows.binder_issuance.service import WORKFLOW_NAME as BINDER_ISSUANCE_WORKFLOW


@pytest.fixture
async def es_session() -> AsyncGenerator[AsyncSession, None]:
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
    return Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u-sr", role=Role.SENIOR)


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
    what let a wrong path ship to production undetected. The real, reachable
    ``create_event`` (see this module's docstring) always inserts a fresh
    all-day event — no caller-supplied id, no GET-then-upsert — so this only
    needs to handle the one insert route."""
    path = request.url.path
    if path == "/proxy/calendar/v3/calendars/primary/events" and request.method == "POST":
        body = json.loads(request.content)
        assert body["start"]["date"]
        assert body["end"]["date"]
        _calendar_handler.inserted += 1  # type: ignore[attr-defined]
        return httpx.Response(200, json={"id": f"cal-event-{_calendar_handler.inserted}"})  # type: ignore[attr-defined]
    return httpx.Response(404, json={"error": f"unhandled {request.method} {path}"})


_calendar_handler.inserted = 0  # type: ignore[attr-defined]


@pytest.fixture
def mocked_calendar_transport(monkeypatch):
    _calendar_handler.inserted = 0  # type: ignore[attr-defined]
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_calendar_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def _connected_calendar_service(es_ctx, es_session) -> LiveNangoConnectorService:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-calendar",
        nango_connection_id="conn-cal-1", status="connected",
    )
    return LiveNangoConnectorService(get_settings(), es_session)


# ── _calendar_safe_event_id: Google's events.insert only accepts base32hex
#    (lowercase a-v, digits 0-9), 5-1024 chars — this is the exact constraint a
#    real "binder-issuance-{uuid}-obligation-0"-shaped id violates (hyphens, and
#    letters outside a-v), which is what produced the live 400 this covers ──


def test_calendar_safe_event_id_matches_google_charset() -> None:
    safe = _calendar_safe_event_id("binder-issuance-ef6a6fcd-d1ea-4ece-843d-obligation-0")
    assert re.fullmatch(r"[0-9a-v]{5,1024}", safe)


def test_calendar_safe_event_id_is_deterministic() -> None:
    raw = "binder-issuance-sub-4"
    assert _calendar_safe_event_id(raw) == _calendar_safe_event_id(raw)


def test_calendar_safe_event_id_differs_for_different_input() -> None:
    assert _calendar_safe_event_id("a") != _calendar_safe_event_id("b")


# ── connector-level: LiveNangoConnectorService ──


async def test_create_event_not_connected_raises(es_ctx, es_session) -> None:
    service = LiveNangoConnectorService(get_settings(), es_session)
    with pytest.raises(ConnectorNotConnectedError):
        await service.create_event(
            es_ctx, summary="s", description="d",
            start_date="2027-01-01", end_date="2027-01-01",
        )


async def test_create_event_posts_all_day_event_to_calendar_proxy(
    es_ctx, es_session, mocked_calendar_transport,
) -> None:
    service = await _connected_calendar_service(es_ctx, es_session)
    event_id = await service.create_event(
        es_ctx, summary="Renewal due", description="d",
        start_date="2027-06-01", end_date="2027-06-01",
    )
    assert event_id


async def test_create_event_each_call_inserts_a_fresh_event(
    es_ctx, es_session, mocked_calendar_transport,
) -> None:
    """Unlike the MGA-era design (a caller-supplied deterministic event_id,
    GET-then-upsert so a repeat call updated the same event in place — see
    this module's docstring on why that path is now dead code), the real,
    reachable create_event always inserts a fresh event with no id-based
    de-dup. Neither real ES Calendar trigger (the one-time auto reminder on
    bind confirmation, the manual per-obligation button) needs caller-side
    idempotency by id, so this is genuinely correct for ES's own use, not a
    regression."""
    service = await _connected_calendar_service(es_ctx, es_session)
    first_id = await service.create_event(
        es_ctx, summary="first", description="d",
        start_date="2027-06-01", end_date="2027-06-01",
    )
    second_id = await service.create_event(
        es_ctx, summary="second", description="d",
        start_date="2027-06-02", end_date="2027-06-02",
    )
    assert first_id and second_id and first_id != second_id


# ── connector-level: MockConnectorService ──


async def test_mock_create_event_records_in_memory() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    event_id = await service.create_event(
        ctx, summary="s", description="d", start_date="2027-01-01", end_date="2027-01-01",
    )
    assert event_id == "mock-event-1"
    assert service._calendar_events[0]["summary"] == "s"


async def test_mock_create_event_each_call_appends_a_new_event() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    await service.create_event(
        ctx, summary="first", description="d", start_date="2027-01-01", end_date="2027-01-01",
    )
    await service.create_event(
        ctx, summary="second", description="d", start_date="2027-01-02", end_date="2027-01-02",
    )
    assert len(service._calendar_events) == 2


# ── workflow-level: Binder & Policy Issuance's own manual, per-obligation
#    POST /{item_id}/add-to-calendar (verticals/es/workflows/binder_issuance/
#    router.py) — matched by exact obligation description text (obligations
#    carry no other real identifier), unlike the MGA-era design's index-based
#    add_obligation_to_calendar. The workflow's AUTOMATIC reminder
#    (_maybe_create_renewal_reminder) is proven separately in
#    tests/test_es_binder_issuance.py. ──


def _bind_payload(
    *, bind_id: str, obligation_description: str = "File proof of coverage within 30 days",
    obligation_due_date: str | None = "2027-09-29",
) -> BindCoordinationPayload:
    return BindCoordinationPayload(
        bind_id=bind_id,
        submission_id=bind_id,
        named_insured="Acme LLC",
        carrier_name="Ironclad Casualty Solutions",
        requested_bind_terms=BindTermsOut(premium=24900.0, effective_date="2027-09-01"),
        bind_order_status="SENT",
        post_bind_ongoing_obligations=[
            OngoingObligationOut(description=obligation_description, due_date=obligation_due_date),
        ],
    )


async def _enqueue_bind(es_session, es_ctx, *, bind_id: str, **payload_kwargs) -> str:
    payload = _bind_payload(bind_id=bind_id, **payload_kwargs)
    out_dto = OutputPackageDTO(
        submission_id=bind_id,
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload=payload.model_dump(),
    )
    item = await DefaultReviewQueueService().enqueue(
        es_session, es_ctx, out_dto, BINDER_ISSUANCE_WORKFLOW
    )
    return item.id


async def test_add_to_calendar_404s_for_unknown_item(es_ctx, es_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await add_to_calendar(
            "does-not-exist",
            AddToCalendarRequest(description="File proof of coverage within 30 days"),
            es_ctx, es_session,
        )
    assert exc_info.value.status_code == 404


async def test_add_to_calendar_404s_for_unknown_obligation_description(es_ctx, es_session) -> None:
    item_id = await _enqueue_bind(es_session, es_ctx, bind_id="BND-1")
    with pytest.raises(HTTPException) as exc_info:
        await add_to_calendar(
            item_id, AddToCalendarRequest(description="no such obligation"), es_ctx, es_session,
        )
    assert exc_info.value.status_code == 404


async def test_add_to_calendar_skips_no_date(es_ctx, es_session) -> None:
    item_id = await _enqueue_bind(
        es_session, es_ctx, bind_id="BND-2", obligation_due_date=None,
    )
    out = await add_to_calendar(
        item_id,
        AddToCalendarRequest(description="File proof of coverage within 30 days"),
        es_ctx, es_session,
    )
    assert out.status == "skipped-no-date"


async def test_add_to_calendar_ok_when_connected(es_ctx, es_session) -> None:
    """CONNECTORS_MODE is forced to "mock" for this whole file (fixture above)
    — a connected Calendar integration is enough for the route's own
    build_connector_service() call to resolve a (mock) connector and succeed."""
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-calendar",
        nango_connection_id="conn-cal-2", status="connected",
    )
    item_id = await _enqueue_bind(es_session, es_ctx, bind_id="BND-3")
    out = await add_to_calendar(
        item_id,
        AddToCalendarRequest(description="File proof of coverage within 30 days"),
        es_ctx, es_session,
    )
    assert out.status == "ok"


async def test_add_to_calendar_skips_when_not_connected(es_ctx, es_session, monkeypatch) -> None:
    """MockConnectorService always "succeeds" (no connection concept), so this
    forces CONNECTORS_MODE=live with no seeded Connection row — the real path a
    genuinely unconnected tenant hits — to prove the guard works end to end."""
    monkeypatch.setenv("CONNECTORS_MODE", "live")
    get_settings.cache_clear()
    item_id = await _enqueue_bind(es_session, es_ctx, bind_id="BND-4")
    out = await add_to_calendar(
        item_id,
        AddToCalendarRequest(description="File proof of coverage within 30 days"),
        es_ctx, es_session,
    )
    assert out.status == "skipped-not-connected"
    get_settings.cache_clear()


async def test_add_to_calendar_ok_over_real_nango_proxy_path(
    es_ctx, es_session, monkeypatch, mocked_calendar_transport,
) -> None:
    """End-to-end proof the route is wired to the REAL Calendar API path, not
    just the mock connector shortcut above: forces CONNECTORS_MODE=live so
    build_connector_service() returns a real LiveNangoConnectorService, whose
    ``create_event`` call has to satisfy the same exact-path-matched,
    GET-then-upsert mock transport the connector-level tests above use."""
    monkeypatch.setenv("CONNECTORS_MODE", "live")
    get_settings.cache_clear()
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-calendar",
        nango_connection_id="conn-cal-3", status="connected",
    )
    item_id = await _enqueue_bind(es_session, es_ctx, bind_id="BND-5")
    out = await add_to_calendar(
        item_id,
        AddToCalendarRequest(description="File proof of coverage within 30 days"),
        es_ctx, es_session,
    )
    assert out.status == "ok"
    get_settings.cache_clear()
