"""Product-wide static-data fallback (core.data_mode): resolver triggers,
connector-factory wiring, LLM-layer wiring, and the /data-mode endpoint."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import core.models  # noqa: F401  (registers tables)
from core import data_mode
from core.common.dtos import Ctx
from core.common.enums import Role, Vertical
from core.config import get_settings
from core.data_mode import (
    DataMode,
    clear_llm_quota_flag,
    llm_quota_active,
    note_llm_quota_error,
    resolve_data_mode,
)
from core.ingestion.connectors import (
    ConnectorNotConnectedError,
    MockConnectorService,
    StaticFallbackConnectorService,
    build_connector_service,
)
from core.llm.service import MockLLMProvider, OpenAIProvider, build_llm_service
from core.models import Connection, Tenant


@pytest.fixture(autouse=True)
def _clean_quota_flag():
    clear_llm_quota_flag()
    data_mode.invalidate_connection_cache()
    yield
    clear_llm_quota_flag()
    data_mode.invalidate_connection_cache()


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(Tenant(id="demo-es", name="Demo E&S", vertical=Vertical.ES))
        await s.commit()
        yield s
    await engine.dispose()


# --- resolver -----------------------------------------------------------------


async def test_mock_mode_resolves_static(session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "mock")
    assert await resolve_data_mode(session, "demo-es") == DataMode("static", "mock_mode")


async def test_live_but_disconnected_resolves_static(session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "live")
    assert await resolve_data_mode(session, "demo-es") == DataMode(
        "static", "connector_disconnected"
    )


async def test_live_and_connected_resolves_live(session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "live")
    session.add(
        Connection(
            tenant_id="demo-es",
            provider=get_settings().nango_integration_mail,
            status="connected",
            nango_connection_id="nc-1",
        )
    )
    await session.commit()
    assert await resolve_data_mode(session, "demo-es") == DataMode("live", "")


async def test_llm_quota_flag_wins_even_when_connected(session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "live")
    session.add(
        Connection(
            tenant_id="demo-es",
            provider=get_settings().nango_integration_mail,
            status="connected",
            nango_connection_id="nc-1",
        )
    )
    await session.commit()
    note_llm_quota_error()
    assert await resolve_data_mode(session, "demo-es") == DataMode(
        "static", "llm_insufficient_quota"
    )


def test_quota_flag_expires(monkeypatch) -> None:
    note_llm_quota_error()
    assert llm_quota_active()
    monkeypatch.setattr(data_mode, "_LLM_QUOTA_FLAG_TTL_SECONDS", -1.0)
    assert not llm_quota_active()  # expired flags self-clear


# --- connector factory wiring ---------------------------------------------------


async def test_factory_live_wraps_with_static_fallback(session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "live")
    svc = build_connector_service(workflow_n=10, session=session, tenant_id="demo-es")
    assert isinstance(svc, StaticFallbackConnectorService)

    # Disconnected live connector falls back to the SAME fixture path as mock
    # mode instead of raising toward a 428.
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.JUNIOR)
    mock_inbox = await MockConnectorService(workflow_n=10).fetch_inbox(ctx)
    fallback_inbox = await svc.fetch_inbox(ctx)  # live raises -> mock served
    assert [m.id for m in fallback_inbox] == [m.id for m in mock_inbox]


def test_factory_quota_flag_returns_mock(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "live")
    note_llm_quota_error()
    svc = build_connector_service(workflow_n=10)
    assert isinstance(svc, MockConnectorService)


def test_factory_mock_mode_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "mock")
    assert isinstance(build_connector_service(workflow_n=10), MockConnectorService)


# --- LLM wiring ------------------------------------------------------------------


def test_llm_factory_mock_mode_never_builds_live_provider(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "mock")
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-real-key")
    svc = build_llm_service()
    assert isinstance(svc._provider, MockLLMProvider)


def test_llm_factory_quota_flag_forces_mock(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "live")
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-real-key")
    note_llm_quota_error()
    svc = build_llm_service()
    assert isinstance(svc._provider, MockLLMProvider)


def test_llm_factory_live_when_funded_and_live(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "connectors_mode", "live")
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-real-key")
    svc = build_llm_service()
    assert isinstance(svc._provider, OpenAIProvider)


async def test_openai_quota_error_sets_flag_and_falls_back(monkeypatch) -> None:
    """A live call failing with insufficient_quota returns the deterministic
    mock output for THAT request and flips the product-wide flag."""

    class _QuotaExc(Exception):
        status_code = 429

    class _FailingClient:
        class chat:  # noqa: N801 — mirrors SDK shape
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise _QuotaExc("insufficient_quota")

    provider = OpenAIProvider("sk-real-key")
    provider._client = _FailingClient()
    text = await provider.complete(model="m", system="s", user="grounded facts")
    assert text.startswith("[mock:m]")
    assert llm_quota_active()

    # While flagged, subsequent calls skip the live client entirely.
    provider._client = None  # a real client would be constructed if called
    text2 = await provider.complete(model="m", system="s", user="grounded facts")
    assert text2.startswith("[mock:m]")
    assert provider._client is None  # untouched — no live call attempted


async def test_openai_non_billing_errors_still_raise(monkeypatch) -> None:
    class _OtherExc(Exception):
        status_code = 500

    class _FailingClient:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs):
                    raise _OtherExc("boom")

    provider = OpenAIProvider("sk-real-key")
    provider._client = _FailingClient()
    with pytest.raises(_OtherExc):
        await provider.complete(model="m", system="s", user="u")
    assert not llm_quota_active()


# --- endpoint ---------------------------------------------------------------------


async def test_data_mode_endpoint(session, monkeypatch) -> None:
    from core.app_config.router import get_data_mode

    monkeypatch.setattr(get_settings(), "connectors_mode", "mock")
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.JUNIOR)
    out = await get_data_mode(ctx, session)
    assert out.mode == "static" and out.reason == "mock_mode"

    monkeypatch.setattr(get_settings(), "connectors_mode", "live")
    out = await get_data_mode(ctx, session)
    assert out.mode == "static" and out.reason == "connector_disconnected"
