"""Proves the Slack write-back fallback added for Renewal Remarketing (a
real notification on URGENT_REMARKET, the PRD's own "zero missed urgent
triggers" hard gate): connector-level send against a mocked Nango Slack
proxy (httpx.MockTransport, no real network), the ``resolve_channel_id`` /
``try_notify_slack`` helpers' graceful-skip paths, and the
``PATCH /connections/{provider}/channel-id`` endpoint. Mirrors
test_calendar_writeback.py / test_sheets_writeback.py's pattern exactly.
Gmail/Sheets/Calendar/Drive/mock-connector behavior is untouched.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import core.models  # noqa: F401  (registers tables)
from core.common.dtos import Ctx
from core.common.enums import Role, Vertical
from core.config import get_settings
from core.ingestion.connectors import (
    ConnectorNotConnectedError,
    LiveNangoConnectorService,
    MockConnectorService,
)
from core.ingestion.slack_writeback import resolve_channel_id, try_notify_slack
from core.integrations.repository import upsert_connection
from core.integrations.router import ChannelIdRequest, set_channel_id
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
    monkeypatch.setenv("CONNECTORS_MODE", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _slack_handler(request: httpx.Request) -> httpx.Response:
    """Pins the real Slack Web API path exactly (``/proxy/api/chat.postMessage``)."""
    path = request.url.path
    if path == "/proxy/api/chat.postMessage" and request.method == "POST":
        body = json.loads(request.content)
        assert body["channel"] and body["text"]
        return httpx.Response(200, json={"ok": True, "ts": "1234.5678"})
    return httpx.Response(404, json={"error": f"unhandled {request.method} {path}"})


@pytest.fixture
def mocked_slack_transport(monkeypatch):
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_slack_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def _connected_slack_service(es_ctx, es_session) -> LiveNangoConnectorService:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "slack",
        nango_connection_id="conn-slack-1", status="connected",
    )
    return LiveNangoConnectorService(get_settings(), es_session)


# ── connector-level: LiveNangoConnectorService ──


async def test_send_slack_message_not_connected_raises(es_ctx, es_session) -> None:
    service = LiveNangoConnectorService(get_settings(), es_session)
    with pytest.raises(ConnectorNotConnectedError):
        await service.send_slack_message(es_ctx, channel="C123", text="hi")


async def test_send_slack_message_posts_to_slack_proxy(
    es_ctx, es_session, mocked_slack_transport
) -> None:
    service = await _connected_slack_service(es_ctx, es_session)
    ts = await service.send_slack_message(es_ctx, channel="C123", text="URGENT_REMARKET: Acme LLC")
    assert ts == "1234.5678"


# ── connector-level: MockConnectorService ──


async def test_mock_send_slack_message_records_in_memory() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    message_id = await service.send_slack_message(ctx, channel="C123", text="hi")
    assert message_id == "mock-slack-1"
    assert service._slack_messages == [{"id": "mock-slack-1", "channel": "C123", "text": "hi"}]


# ── resolve_channel_id: reads the tenant's own Connection row, never .env ──


async def test_resolve_channel_id_empty_when_not_connected(es_ctx, es_session) -> None:
    channel_id = await resolve_channel_id(es_session, es_ctx.tenant_id, get_settings())
    assert channel_id == ""


async def test_resolve_channel_id_empty_when_connected_but_unset(es_ctx, es_session) -> None:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "slack",
        nango_connection_id="conn-slack-2", status="connected",
    )
    channel_id = await resolve_channel_id(es_session, es_ctx.tenant_id, get_settings())
    assert channel_id == ""


async def test_resolve_channel_id_reads_tenants_own_connection(es_ctx, es_session) -> None:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "slack",
        nango_connection_id="conn-slack-3", status="connected", channel_id="C-real-123",
    )
    channel_id = await resolve_channel_id(es_session, es_ctx.tenant_id, get_settings())
    assert channel_id == "C-real-123"


# ── try_notify_slack helper: never raises, reports status ──


async def test_try_notify_slack_skips_without_channel_id() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    status = await try_notify_slack(MockConnectorService(), ctx, "", "hi")
    assert status == "skipped-no-channel-id"


async def test_try_notify_slack_skips_when_not_connected(es_ctx, es_session) -> None:
    connector = LiveNangoConnectorService(get_settings(), es_session)
    status = await try_notify_slack(connector, es_ctx, "C123", "hi")
    assert status == "skipped-not-connected"


async def test_try_notify_slack_ok_when_connected(
    es_ctx, es_session, mocked_slack_transport
) -> None:
    connector = await _connected_slack_service(es_ctx, es_session)
    status = await try_notify_slack(connector, es_ctx, "C123", "URGENT_REMARKET: Acme LLC")
    assert status == "ok"


# ── PATCH /connections/{provider}/channel-id (Integrations page) ──


async def test_set_channel_id_rejects_non_slack_provider(es_ctx, es_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await set_channel_id(
            "google-mail", ChannelIdRequest(channel_id="C123"), es_ctx, es_session, get_settings()
        )
    assert exc_info.value.status_code == 400


async def test_set_channel_id_requires_connected_first(es_ctx, es_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await set_channel_id(
            "slack", ChannelIdRequest(channel_id="C123"), es_ctx, es_session, get_settings()
        )
    assert exc_info.value.status_code == 409


async def test_set_channel_id_rejects_blank_value(es_ctx, es_session) -> None:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "slack",
        nango_connection_id="conn-slack-4", status="connected",
    )
    with pytest.raises(HTTPException) as exc_info:
        await set_channel_id(
            "slack", ChannelIdRequest(channel_id="   "), es_ctx, es_session, get_settings()
        )
    assert exc_info.value.status_code == 400


async def test_set_channel_id_persists_when_connected(es_ctx, es_session) -> None:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "slack",
        nango_connection_id="conn-slack-5", status="connected",
    )
    out = await set_channel_id(
        "slack", ChannelIdRequest(channel_id=" C-real-xyz "), es_ctx, es_session, get_settings(),
    )
    assert out.channel_id == "C-real-xyz"

    resolved = await resolve_channel_id(es_session, es_ctx.tenant_id, get_settings())
    assert resolved == "C-real-xyz"
