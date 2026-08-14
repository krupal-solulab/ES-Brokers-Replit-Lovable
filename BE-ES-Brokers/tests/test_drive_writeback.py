"""Proves the Google Drive write-back fallback added for Binder & Policy
Issuance (a real archive copy of the issued policy document, uploaded once
reconciliation confirms it's clean): connector-level create+upload against a
mocked Nango Drive proxy (httpx.MockTransport, no real network), plus the
``try_archive_document`` helper's graceful-skip paths. Mirrors
test_calendar_writeback.py's pattern exactly. Gmail/Sheets/Calendar/
mock-connector behavior is untouched.
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
from core.ingestion.connectors import (
    ConnectorNotConnectedError,
    LiveNangoConnectorService,
    MockConnectorService,
)
from core.ingestion.drive_writeback import try_archive_document
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
    monkeypatch.setenv("CONNECTORS_MODE", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _drive_handler(request: httpx.Request) -> httpx.Response:
    """Pins the real Google Drive API paths exactly: metadata-only create
    (``/proxy/drive/v3/files``) then a media upload
    (``/proxy/upload/drive/v3/files/{id}?uploadType=media``)."""
    path = request.url.path
    if path == "/proxy/drive/v3/files" and request.method == "POST":
        body = json.loads(request.content)
        assert body["name"]
        return httpx.Response(200, json={"id": "drive-file-1"})
    if path == "/proxy/upload/drive/v3/files/drive-file-1" and request.method == "PATCH":
        assert request.url.params.get("uploadType") == "media"
        return httpx.Response(200, json={"id": "drive-file-1"})
    return httpx.Response(404, json={"error": f"unhandled {request.method} {path}"})


@pytest.fixture
def mocked_drive_transport(monkeypatch):
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_drive_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def _connected_drive_service(es_ctx, es_session) -> LiveNangoConnectorService:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-drive",
        nango_connection_id="conn-drive-1", status="connected",
    )
    return LiveNangoConnectorService(get_settings(), es_session)


# ── connector-level: LiveNangoConnectorService ──


async def test_upload_file_not_connected_raises(es_ctx, es_session) -> None:
    service = LiveNangoConnectorService(get_settings(), es_session)
    with pytest.raises(ConnectorNotConnectedError):
        await service.upload_file(es_ctx, filename="policy.txt", content="...")


async def test_upload_file_creates_and_uploads_to_drive_proxy(
    es_ctx, es_session, mocked_drive_transport
) -> None:
    service = await _connected_drive_service(es_ctx, es_session)
    file_id = await service.upload_file(
        es_ctx, filename="Acme LLC - Issued Policy.txt", content="policy text"
    )
    assert file_id == "drive-file-1"


# ── connector-level: MockConnectorService ──


async def test_mock_upload_file_records_in_memory() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    file_id = await service.upload_file(ctx, filename="policy.txt", content="policy text")
    assert file_id == "mock-file-policy.txt"
    assert service._drive_files["policy.txt"] == "policy text"


# ── try_archive_document helper: never raises, reports status ──


async def test_try_archive_document_skips_without_content() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    status = await try_archive_document(
        MockConnectorService(), ctx, filename="policy.txt", content=None
    )
    assert status == "skipped-no-content"

    status_empty = await try_archive_document(
        MockConnectorService(), ctx, filename="policy.txt", content=""
    )
    assert status_empty == "skipped-no-content"


async def test_try_archive_document_skips_when_not_connected(es_ctx, es_session) -> None:
    connector = LiveNangoConnectorService(get_settings(), es_session)
    status = await try_archive_document(
        connector, es_ctx, filename="policy.txt", content="policy text"
    )
    assert status == "skipped-not-connected"


async def test_try_archive_document_ok_when_connected(
    es_ctx, es_session, mocked_drive_transport
) -> None:
    connector = await _connected_drive_service(es_ctx, es_session)
    status = await try_archive_document(
        connector, es_ctx, filename="Acme LLC - Issued Policy.txt", content="policy text"
    )
    assert status == "ok"


async def test_try_archive_document_records_real_content_in_mock() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    connector = MockConnectorService()
    status = await try_archive_document(
        connector, ctx, filename="Acme LLC - Issued Policy - BIND-1.txt",
        content="POLICY DECLARATIONS PAGE...",
    )
    assert status == "ok"
    assert connector._drive_files["Acme LLC - Issued Policy - BIND-1.txt"] == (
        "POLICY DECLARATIONS PAGE..."
    )
