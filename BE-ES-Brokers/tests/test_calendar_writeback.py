"""Proves the Google Calendar write-back fallback added for Binder & Policy
Issuance (a real renewal-reminder event ~60 days before the bound policy's
expiration date): connector-level create-event against a mocked Nango
Calendar proxy (httpx.MockTransport, no real network), plus the
``try_create_renewal_reminder`` helper's graceful-skip paths. Mirrors
test_sheets_writeback.py's pattern exactly. Gmail/Sheets/mock-connector
behavior is untouched.
"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import core.models  # noqa: F401  (registers tables)
from core.common.dtos import Ctx
from core.common.enums import Role, Vertical
from core.config import get_settings
from core.ingestion.calendar_writeback import (
    RENEWAL_REMINDER_DAYS_BEFORE_EXPIRATION,
    try_create_renewal_reminder,
)
from core.ingestion.connectors import (
    ConnectorNotConnectedError,
    LiveNangoConnectorService,
    MockConnectorService,
)
from core.integrations.repository import upsert_connection
from core.models import Tenant


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
    return Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)


@pytest.fixture(autouse=True)
def _force_mock_connectors_mode(monkeypatch):
    """The real .env sets CONNECTORS_MODE=live for this deployment — force
    "mock" for every test in this file unless a test explicitly builds its own
    LiveNangoConnectorService directly (same fix used by test_sheets_writeback.py)."""
    monkeypatch.setenv("CONNECTORS_MODE", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _calendar_handler(request: httpx.Request) -> httpx.Response:
    """Pins the real Google Calendar API path exactly
    (``/proxy/calendar/v3/calendars/primary/events``)."""
    path = request.url.path
    if path == "/proxy/calendar/v3/calendars/primary/events" and request.method == "POST":
        body = json.loads(request.content)
        assert body["start"]["date"] and body["end"]["date"]  # all-day, never dateTime
        return httpx.Response(200, json={"id": "cal-event-1"})
    return httpx.Response(404, json={"error": f"unhandled {request.method} {path}"})


@pytest.fixture
def mocked_calendar_transport(monkeypatch):
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


# ── connector-level: LiveNangoConnectorService ──


async def test_create_event_not_connected_raises(es_ctx, es_session) -> None:
    service = LiveNangoConnectorService(get_settings(), es_session)
    with pytest.raises(ConnectorNotConnectedError):
        await service.create_event(
            es_ctx, summary="s", description="d", start_date="2028-07-01", end_date="2028-07-02"
        )


async def test_create_event_posts_to_calendar_proxy(
    es_ctx, es_session, mocked_calendar_transport
) -> None:
    service = await _connected_calendar_service(es_ctx, es_session)
    event_id = await service.create_event(
        es_ctx, summary="Acme LLC — renewal check (Ironclad)",
        description="Policy expires 2028-09-01.",
        start_date="2028-07-03", end_date="2028-07-04",
    )
    assert event_id == "cal-event-1"


# ── connector-level: MockConnectorService ──


async def test_mock_create_event_records_in_memory() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    event_id = await service.create_event(
        ctx, summary="s", description="d", start_date="2028-07-03", end_date="2028-07-04"
    )
    assert event_id == "mock-event-1"
    assert service._calendar_events == [
        {"id": "mock-event-1", "summary": "s", "description": "d",
         "start_date": "2028-07-03", "end_date": "2028-07-04"}
    ]


# ── try_create_renewal_reminder helper: never raises, reports status ──


async def test_try_create_renewal_reminder_skips_without_expiration_date() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    status = await try_create_renewal_reminder(
        MockConnectorService(), ctx, named_insured="Acme", carrier_name="Ironclad",
        expiration_date=None,
    )
    assert status == "skipped-no-date"


async def test_try_create_renewal_reminder_skips_malformed_date() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    status = await try_create_renewal_reminder(
        MockConnectorService(), ctx, named_insured="Acme", carrier_name="Ironclad",
        expiration_date="not-a-date",
    )
    assert status == "skipped-no-date"


async def test_try_create_renewal_reminder_skips_when_not_connected(es_ctx, es_session) -> None:
    connector = LiveNangoConnectorService(get_settings(), es_session)
    status = await try_create_renewal_reminder(
        connector, es_ctx, named_insured="Acme", carrier_name="Ironclad",
        expiration_date="2028-09-01",
    )
    assert status == "skipped-not-connected"


async def test_try_create_renewal_reminder_ok_when_connected(
    es_ctx, es_session, mocked_calendar_transport
) -> None:
    connector = await _connected_calendar_service(es_ctx, es_session)
    status = await try_create_renewal_reminder(
        connector, es_ctx, named_insured="Acme", carrier_name="Ironclad",
        expiration_date="2028-09-01",
    )
    assert status == "ok"


async def test_try_create_renewal_reminder_uses_mock_and_computes_real_date() -> None:
    """The reminder date is genuinely computed (expiration minus the real
    threshold), never hardcoded — proven against the in-memory mock connector
    so the exact recorded date can be asserted."""
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    connector = MockConnectorService()
    status = await try_create_renewal_reminder(
        connector, ctx, named_insured="Acme LLC", carrier_name="Ironclad Casualty Solutions",
        expiration_date="2028-09-01",
    )
    assert status == "ok"
    assert len(connector._calendar_events) == 1
    event = connector._calendar_events[0]
    assert "Acme LLC" in event["summary"]
    assert "Ironclad Casualty Solutions" in event["summary"]
    assert RENEWAL_REMINDER_DAYS_BEFORE_EXPIRATION == 60
    assert event["start_date"] == "2028-07-03"  # 2028-09-01 minus 60 days
    assert event["end_date"] == "2028-07-04"
