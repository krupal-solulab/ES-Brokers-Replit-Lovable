"""Proves the Drive-upload fallback (docs/CONNECTORS_NANGO.md): connector-level
put_file against a mocked Nango Drive proxy (httpx.MockTransport, no real
network), the (now vertical-agnostic, currently unused by any ES workflow)
PDF generators, and the two real ES workflows that actually archive to Drive —
Diligent Search & Compliance Documentation's manual, per-state
``POST /{item_id}/save-to-drive`` (``verticals/es/workflows/diligent_search/
router.py``, exercised directly here) and Binder & Policy Issuance's automatic
``_maybe_archive_issued_policy`` (fires once an issued policy reconciles CLEAN
— already covered end-to-end in tests/test_es_binder_issuance.py's
``test_attach_live_policy_archives_to_drive_when_clean``, not duplicated here).
Unlike the MGA-era design this backend used to have (a page-level bulk
"export every item into one PDF" button per workflow), neither real ES Drive
write-back is a bulk action — there is no bulk-upload equivalent here, so no
test asserts one. Mirrors test_sheets_writeback.py's pattern.
"""

from __future__ import annotations

import io
import json
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import HTTPException
from pypdf import PdfReader
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
)
from core.ingestion.pdf_export import render_bulk_summary_pdf, render_summary_pdf
from core.ingestion.writeback import extract_folder_id, resolve_drive_folder_id, try_put_file
from core.integrations.repository import upsert_connection
from core.models import Tenant
from core.review_queue import DefaultReviewQueueService
from verticals.es.workflows.diligent_search.router import SaveToDriveRequest, save_to_drive
from verticals.es.workflows.diligent_search.schema import (
    ComplianceRecordPayload,
    StateDeterminationOut,
)
from verticals.es.workflows.diligent_search.service import WORKFLOW_NAME as DILIGENT_SEARCH_WORKFLOW


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
    for every test in this file so a workflow route's upload call never attempts
    a real Nango request via build_connector_service."""
    monkeypatch.setenv("CONNECTORS_MODE", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _drive_handler(request: httpx.Request) -> httpx.Response:
    """Exact-path-matched, per the lesson from Sheets: a loose match is exactly
    what let a wrong path ship to production undetected. Uploads use a DIFFERENT
    host path than metadata-only calls (upload/drive/v3/files, not drive/v3/files).
    Shared by both ``put_file`` (connector-level tests below) and ``upload_file``
    (the workflow-level ``save_to_drive`` route below) — both hit this exact
    same pair of real Drive API paths."""
    path = request.url.path
    if path == "/proxy/drive/v3/files" and request.method == "POST":
        body = json.loads(request.content)
        assert body["name"]
        return httpx.Response(200, json={"id": "drive-file-1", "name": body["name"]})
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


# ── extract_folder_id: a pasted URL must never reach the Drive proxy verbatim ──


def test_extract_folder_id_from_bare_id() -> None:
    assert extract_folder_id("1AbCdEfGhIjKlMnOpQrS") == "1AbCdEfGhIjKlMnOpQrS"


def test_extract_folder_id_from_full_url() -> None:
    url = "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrS?usp=sharing"
    assert extract_folder_id(url) == "1AbCdEfGhIjKlMnOpQrS"


def test_extract_folder_id_from_shared_drive_url() -> None:
    url = "https://drive.google.com/drive/u/0/folders/1AbCdEfGhIjKlMnOpQrS"
    assert extract_folder_id(url) == "1AbCdEfGhIjKlMnOpQrS"


# ── render_summary_pdf / render_bulk_summary_pdf: pure, vertical-agnostic core
#    helpers — proven here regardless of whether any ES workflow calls them
#    today (neither does; both remain available core plumbing) ──


def test_render_summary_pdf_produces_real_pdf_with_expected_text() -> None:
    pdf_bytes = render_summary_pdf(
        "Bind Order Summary — BND-1",
        [("Bind ID", "BND-1"), ("Status", "READY")],
    )
    assert pdf_bytes.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = reader.pages[0].extract_text()
    assert "Bind Order Summary" in text
    assert "BND-1" in text
    assert "READY" in text


def test_render_bulk_summary_pdf_one_page_per_item() -> None:
    pdf_bytes = render_bulk_summary_pdf(
        "Bind Issuance",
        [
            [("Bind ID", "BND-A"), ("Status", "READY")],
            [("Bind ID", "BND-B"), ("Status", "BLOCKED")],
        ],
    )
    assert pdf_bytes.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 2
    page1 = reader.pages[0].extract_text()
    page2 = reader.pages[1].extract_text()
    assert "BND-A" in page1 and "READY" in page1
    assert "BND-B" in page2 and "BLOCKED" in page2


def test_render_bulk_summary_pdf_empty_list_is_still_valid() -> None:
    pdf_bytes = render_bulk_summary_pdf("Bind Issuance", [])
    assert pdf_bytes.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1
    assert "No items to export" in reader.pages[0].extract_text()


# ── connector-level: LiveNangoConnectorService ──


async def test_put_file_not_connected_raises(es_ctx, es_session) -> None:
    service = LiveNangoConnectorService(get_settings(), es_session)
    with pytest.raises(ConnectorNotConnectedError):
        await service.put_file(es_ctx, "", "test.pdf", b"data", "application/pdf")


async def test_put_file_creates_metadata_then_uploads_content(
    es_ctx, es_session, mocked_drive_transport
) -> None:
    service = await _connected_drive_service(es_ctx, es_session)
    file_id = await service.put_file(
        es_ctx, "folder-1", "bind-BND-1.pdf", b"%PDF-fake-content", "application/pdf"
    )
    assert file_id == "drive-file-1"


async def test_put_file_omits_parents_when_no_folder_id(
    es_ctx, es_session, mocked_drive_transport
) -> None:
    service = await _connected_drive_service(es_ctx, es_session)
    file_id = await service.put_file(es_ctx, "", "bind-BND-1.pdf", b"data", "application/pdf")
    assert file_id == "drive-file-1"


# ── connector-level: MockConnectorService ──


async def test_mock_put_file_records_in_memory() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    file_id = await service.put_file(ctx, "folder-1", "test.pdf", b"data", "application/pdf")
    assert file_id
    assert service._files == [("folder-1", "test.pdf", b"data", "application/pdf")]


# ── resolve_drive_folder_id: empty is a valid "root Drive" value, not a skip ──


async def test_resolve_drive_folder_id_empty_when_not_connected(es_ctx, es_session) -> None:
    folder_id = await resolve_drive_folder_id(es_session, es_ctx.tenant_id, get_settings())
    assert folder_id == ""


async def test_resolve_drive_folder_id_reads_tenants_own_connection(es_ctx, es_session) -> None:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-drive",
        nango_connection_id="conn-drive-2", status="connected", folder_id="real-folder-abc",
    )
    folder_id = await resolve_drive_folder_id(es_session, es_ctx.tenant_id, get_settings())
    assert folder_id == "real-folder-abc"


# ── try_put_file helper: never raises, reports status ──


async def test_try_put_file_skips_when_not_connected(es_ctx, es_session) -> None:
    connector = LiveNangoConnectorService(get_settings(), es_session)
    status = await try_put_file(connector, es_ctx, "", "test.pdf", b"data", "application/pdf")
    assert status == "skipped-not-connected"


async def test_try_put_file_ok_when_connected(es_ctx, es_session, mocked_drive_transport) -> None:
    connector = await _connected_drive_service(es_ctx, es_session)
    status = await try_put_file(connector, es_ctx, "folder-1", "test.pdf", b"data", "application/pdf")
    assert status == "ok"


async def test_try_put_file_ok_with_no_folder_id(es_ctx, es_session, mocked_drive_transport) -> None:
    """Empty folder id is NOT a skip condition for Drive, unlike Sheets' empty
    sheet_id — it just means upload to the tenant's Drive root."""
    connector = await _connected_drive_service(es_ctx, es_session)
    status = await try_put_file(connector, es_ctx, "", "test.pdf", b"data", "application/pdf")
    assert status == "ok"


# ── workflow-level: Diligent Search & Compliance Documentation's own
#    POST /{item_id}/save-to-drive (verticals/es/workflows/diligent_search/
#    router.py) — a manual, per-state archive action. Broker-triggered, not
#    automatic (the PRD is explicit the workflow "doesn't transmit [the
#    record] anywhere beyond the broker's own file" on its own), unlike the
#    MGA-era bulk "export every item" button — no bulk equivalent exists here.
#    Binder & Policy Issuance's own AUTOMATIC Drive archive
#    (_maybe_archive_issued_policy, fired once an issued policy reconciles
#    CLEAN) is already proven end-to-end in
#    tests/test_es_binder_issuance.py::test_attach_live_policy_archives_to_drive_when_clean
#    — not duplicated here. ──


async def _enqueue_compliance_record(
    es_session, es_ctx, *, compliance_record_id: str, state: str,
    document_generated: bool, generated_document_text: str | None,
    overall_status: str = "COMPLETE",
) -> str:
    payload = ComplianceRecordPayload(
        compliance_record_id=compliance_record_id,
        submission_id=compliance_record_id,
        named_insured="Acme LLC",
        state_determinations=[
            StateDeterminationOut(
                state=state, requirement_status="REQUIRED",
                document_generated=document_generated,
                generated_document_text=generated_document_text,
            ),
        ],
        overall_status=overall_status,
    )
    out_dto = OutputPackageDTO(
        submission_id=compliance_record_id,
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload=payload.model_dump(),
    )
    item = await DefaultReviewQueueService().enqueue(
        es_session, es_ctx, out_dto, DILIGENT_SEARCH_WORKFLOW
    )
    return item.id


async def test_save_to_drive_404s_for_unknown_item(es_ctx, es_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await save_to_drive("does-not-exist", SaveToDriveRequest(state="CA"), es_ctx, es_session)
    assert exc_info.value.status_code == 404


async def test_save_to_drive_404s_for_unknown_state(es_ctx, es_session) -> None:
    item_id = await _enqueue_compliance_record(
        es_session, es_ctx, compliance_record_id="CS-1", state="CA",
        document_generated=True, generated_document_text="Diligent search record for CA.",
    )
    with pytest.raises(HTTPException) as exc_info:
        await save_to_drive(item_id, SaveToDriveRequest(state="TX"), es_ctx, es_session)
    assert exc_info.value.status_code == 404


async def test_save_to_drive_409s_when_no_document_generated_yet(es_ctx, es_session) -> None:
    item_id = await _enqueue_compliance_record(
        es_session, es_ctx, compliance_record_id="CS-2", state="FL",
        document_generated=False, generated_document_text=None,
    )
    with pytest.raises(HTTPException) as exc_info:
        await save_to_drive(item_id, SaveToDriveRequest(state="FL"), es_ctx, es_session)
    assert exc_info.value.status_code == 409


async def test_save_to_drive_ok_when_connected(es_ctx, es_session) -> None:
    """CONNECTORS_MODE is forced to "mock" for this whole file (fixture above)
    — a connected Drive integration is enough for the route's own
    build_connector_service() call to resolve a (mock) connector and succeed."""
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-drive",
        nango_connection_id="conn-drive-3", status="connected",
    )
    item_id = await _enqueue_compliance_record(
        es_session, es_ctx, compliance_record_id="CS-3", state="OR",
        document_generated=True, generated_document_text="Diligent search record for OR.",
    )
    out = await save_to_drive(item_id, SaveToDriveRequest(state="OR"), es_ctx, es_session)
    assert out.status == "ok"


async def test_save_to_drive_skips_when_not_connected(es_ctx, es_session, monkeypatch) -> None:
    """MockConnectorService always "succeeds" (no connection concept), so this
    forces CONNECTORS_MODE=live with no seeded Connection row — the real path a
    genuinely unconnected tenant hits — to prove the guard works end to end."""
    monkeypatch.setenv("CONNECTORS_MODE", "live")
    get_settings.cache_clear()
    item_id = await _enqueue_compliance_record(
        es_session, es_ctx, compliance_record_id="CS-4", state="GA",
        document_generated=True, generated_document_text="Diligent search record for GA.",
    )
    out = await save_to_drive(item_id, SaveToDriveRequest(state="GA"), es_ctx, es_session)
    assert out.status == "skipped-not-connected"
    get_settings.cache_clear()


async def test_save_to_drive_ok_over_real_nango_proxy_path(
    es_ctx, es_session, monkeypatch, mocked_drive_transport,
) -> None:
    """End-to-end proof the route is wired to the REAL Drive API path, not just
    the mock connector shortcut above: forces CONNECTORS_MODE=live so
    build_connector_service() returns a real LiveNangoConnectorService, whose
    ``upload_file`` call has to satisfy the same exact-path-matched mock
    transport the connector-level ``put_file`` tests above use."""
    monkeypatch.setenv("CONNECTORS_MODE", "live")
    get_settings.cache_clear()
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-drive",
        nango_connection_id="conn-drive-4", status="connected",
    )
    item_id = await _enqueue_compliance_record(
        es_session, es_ctx, compliance_record_id="CS-5", state="NV",
        document_generated=True, generated_document_text="Diligent search record for NV.",
    )
    out = await save_to_drive(item_id, SaveToDriveRequest(state="NV"), es_ctx, es_session)
    assert out.status == "ok"
    get_settings.cache_clear()
