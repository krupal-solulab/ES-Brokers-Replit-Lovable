"""Proves the Sheets export fallback (docs/CONNECTORS_NANGO.md): connector-level
append/read against a mocked Nango Sheets proxy (httpx.MockTransport, no real
network), plus the one ES workflow that actually has Sheets write-back —
Pipeline & Carrier Performance Reporting's ``POST /{item_id}/export-to-sheet``
route (``verticals/es/workflows/pipeline_reporting/router.py``). Unlike the
MGA-era design this backend used to have (a page-level bulk "export every
item" button per workflow), ES's export is per-item and manual — there is no
bulk-export equivalent here, so no test asserts one. Mirrors
test_live_nango_connector.py's pattern. Gmail/mock-connector behavior is
untouched.
"""

from __future__ import annotations

import json
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
)
from core.ingestion.writeback import extract_sheet_id, resolve_sheet_id, try_append_rows
from core.integrations.repository import upsert_connection
from core.integrations.router import SheetIdRequest, set_sheet_id
from core.models import Tenant
from core.review_queue import DefaultReviewQueueService
from verticals.es.workflows.pipeline_reporting.router import export_to_sheet
from verticals.es.workflows.pipeline_reporting.schema import PipelineReportPayload
from verticals.es.workflows.pipeline_reporting.service import (
    WORKFLOW_NAME as PIPELINE_REPORTING_WORKFLOW,
)


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
    for every test in this file so a workflow route's write-back call never
    attempts a real Nango request via build_connector_service. get_settings() is
    @lru_cache'd, so the cache must be cleared on both sides of the env-var flip
    (same fix used by the ES live-connector tests, e.g. test_es_endorsement.py's
    live_gmail_connected)."""
    monkeypatch.setenv("CONNECTORS_MODE", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


_EXISTING_TITLES: set[str] = set()  # mutated per-test to simulate tab existence


def _sheets_handler(request: httpx.Request) -> httpx.Response:
    """Pins the REAL Google Sheets API path exactly (``/proxy/v4/spreadsheets/...``
    — no ``sheets/`` segment, unlike Gmail's ``/proxy/gmail/v1/...``), including the
    quoted tab prefix every range must carry (``'Tab Name'!A1``, per the Sheets API's
    own A1-notation rules). A prior version of this handler matched loosely
    (``endswith(':append')``, ``'/values/' in path``) and would have returned 200
    for the wrong path the code briefly used in production (``/proxy/sheets/v4/...``)
    — that loose match is exactly why the live bug wasn't caught here first.
    Exact-match every route on purpose."""
    path = request.url.path
    if path == "/proxy/v4/spreadsheets/sheet-1" and request.method == "GET":
        titles = [{"properties": {"title": t}} for t in _EXISTING_TITLES]
        return httpx.Response(200, json={"sheets": titles})
    if path == "/proxy/v4/spreadsheets/sheet-1:batchUpdate" and request.method == "POST":
        body = json.loads(request.content)
        title = body["requests"][0]["addSheet"]["properties"]["title"]
        _EXISTING_TITLES.add(title)
        return httpx.Response(200, json={"replies": [{"addSheet": {"properties": {}}}]})
    if (
        path == "/proxy/v4/spreadsheets/sheet-1/values/'Bind Issuance'!A1:F1"
        and request.method == "PUT"
    ):
        return httpx.Response(200, json={"updatedCells": 6})
    if (
        path == "/proxy/v4/spreadsheets/sheet-1/values/'Bind Issuance'!A1:append"
        and request.method == "POST"
    ):
        return httpx.Response(200, json={"updates": {"updatedRows": 1}})
    if (
        path == "/proxy/v4/spreadsheets/sheet-1/values/'Test Tab'!A1:append"
        and request.method == "POST"
    ):
        return httpx.Response(200, json={"updates": {"updatedRows": 1}})
    if (
        path == "/proxy/v4/spreadsheets/sheet-1/values/'Test Tab'!A1:B2"
        and request.method == "GET"
    ):
        return httpx.Response(200, json={"values": [["a", "b"]]})
    # Pipeline & Carrier Performance Reporting's own tab (8-column header ->
    # A1:H1) — the one real ES workflow with a Sheets write-back.
    if (
        path == "/proxy/v4/spreadsheets/sheet-1/values/'Pipeline Reporting'!A1:H1"
        and request.method == "PUT"
    ):
        return httpx.Response(200, json={"updatedCells": 8})
    if (
        path == "/proxy/v4/spreadsheets/sheet-1/values/'Pipeline Reporting'!A1:append"
        and request.method == "POST"
    ):
        return httpx.Response(200, json={"updates": {"updatedRows": 1}})
    return httpx.Response(404, json={"error": f"unhandled {request.method} {path}"})


@pytest.fixture
def mocked_sheets_transport(monkeypatch):
    _EXISTING_TITLES.clear()
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_sheets_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    yield
    _EXISTING_TITLES.clear()


async def _connected_sheets_service(es_ctx, es_session) -> LiveNangoConnectorService:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-1", status="connected",
    )
    return LiveNangoConnectorService(get_settings(), es_session)


# ── extract_sheet_id: a pasted URL must never reach the Sheets proxy verbatim ──


def test_extract_sheet_id_from_bare_id() -> None:
    assert extract_sheet_id("1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM") == (
        "1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM"
    )


def test_extract_sheet_id_from_full_edit_url() -> None:
    url = "https://docs.google.com/spreadsheets/d/1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM/edit?gid=0#gid=0"
    assert extract_sheet_id(url) == "1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM"


def test_extract_sheet_id_from_bare_url_no_trailing_segment() -> None:
    url = "https://docs.google.com/spreadsheets/d/1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM"
    assert extract_sheet_id(url) == "1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM"


def test_extract_sheet_id_trims_whitespace() -> None:
    assert extract_sheet_id("  abc123  ") == "abc123"


# ── connector-level: LiveNangoConnectorService ──


async def test_append_rows_not_connected_raises(es_ctx, es_session) -> None:
    service = LiveNangoConnectorService(get_settings(), es_session)
    with pytest.raises(ConnectorNotConnectedError):
        await service.append_rows(es_ctx, "sheet-1", [["x"]], tab="Test Tab")


async def test_append_rows_posts_to_sheets_proxy(
    es_ctx, es_session, mocked_sheets_transport
) -> None:
    service = await _connected_sheets_service(es_ctx, es_session)
    await service.append_rows(es_ctx, "sheet-1", [["BND-1", "READY"]], tab="Test Tab")


async def test_read_range_gets_from_sheets_proxy(
    es_ctx, es_session, mocked_sheets_transport
) -> None:
    service = await _connected_sheets_service(es_ctx, es_session)
    rows = await service.read_range(es_ctx, "sheet-1", "A1:B2", tab="Test Tab")
    assert rows == [["a", "b"]]


async def test_append_rows_creates_tab_and_header_when_missing(
    es_ctx, es_session, mocked_sheets_transport
) -> None:
    """First-ever write to a fresh tab: batchUpdate (addSheet) + values.update
    (header) must both fire before the data-row append."""
    service = await _connected_sheets_service(es_ctx, es_session)
    assert "Bind Issuance" not in _EXISTING_TITLES
    await service.append_rows(
        es_ctx, "sheet-1", [["BND-1", "sub-1", "Acme", "READY", 1000, "2027-01-01"]],
        tab="Bind Issuance",
        header=["Bind ID", "Submission ID", "Named Insured", "Status", "Premium", "Approved At"],
    )
    assert "Bind Issuance" in _EXISTING_TITLES


async def test_append_rows_skips_tab_creation_when_already_exists(
    es_ctx, es_session, mocked_sheets_transport
) -> None:
    """A second write to the same tab must not re-create it or re-write the header
    — only the existence check (GET) + the data append should fire."""
    _EXISTING_TITLES.add("Bind Issuance")
    service = await _connected_sheets_service(es_ctx, es_session)
    await service.append_rows(
        es_ctx, "sheet-1", [["BND-2", "sub-2", "Beta", "READY", 2000, "2027-01-02"]],
        tab="Bind Issuance",
        header=["Bind ID", "Submission ID", "Named Insured", "Status", "Premium", "Approved At"],
    )
    # No error means the handler's exact-match routes were satisfied without an
    # unexpected batchUpdate/update call landing on the (unhandled -> 404) path.


# ── connector-level: MockConnectorService ──


async def test_mock_append_rows_records_in_memory() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    await service.append_rows(ctx, "sheet-1", [["a", "b"]], tab="Test Tab")
    assert await service.read_range(ctx, "sheet-1", "A1", tab="Test Tab") == [["a", "b"]]


async def test_mock_append_rows_isolates_tabs() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    await service.append_rows(ctx, "sheet-1", [["a"]], tab="Tab A")
    await service.append_rows(ctx, "sheet-1", [["b"]], tab="Tab B")
    assert await service.read_range(ctx, "sheet-1", "A1", tab="Tab A") == [["a"]]
    assert await service.read_range(ctx, "sheet-1", "A1", tab="Tab B") == [["b"]]


async def test_mock_append_rows_writes_header_only_once() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    header = ["Col A", "Col B"]
    await service.append_rows(ctx, "sheet-1", [["1", "2"]], tab="Tab A", header=header)
    await service.append_rows(ctx, "sheet-1", [["3", "4"]], tab="Tab A", header=header)
    rows = await service.read_range(ctx, "sheet-1", "A1", tab="Tab A")
    assert rows == [header, ["1", "2"], ["3", "4"]]


# ── resolve_sheet_id: reads the tenant's own Connection row, never .env ──


async def test_resolve_sheet_id_empty_when_not_connected(es_ctx, es_session) -> None:
    sheet_id = await resolve_sheet_id(es_session, es_ctx.tenant_id, get_settings())
    assert sheet_id == ""


async def test_resolve_sheet_id_empty_when_connected_but_unset(es_ctx, es_session) -> None:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-2", status="connected",
    )
    sheet_id = await resolve_sheet_id(es_session, es_ctx.tenant_id, get_settings())
    assert sheet_id == ""


async def test_resolve_sheet_id_reads_tenants_own_connection(es_ctx, es_session) -> None:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-3", status="connected", sheet_id="real-sheet-abc",
    )
    sheet_id = await resolve_sheet_id(es_session, es_ctx.tenant_id, get_settings())
    assert sheet_id == "real-sheet-abc"


# ── try_append_rows helper: never raises, reports status ──


async def test_try_append_rows_skips_without_sheet_id() -> None:
    ctx = Ctx(tenant_id="demo-es", vertical=Vertical.ES, user_id="u", role=Role.SENIOR)
    status = await try_append_rows(MockConnectorService(), ctx, "", [["a"]], tab="Test Tab")
    assert status == "skipped-no-sheet-id"


async def test_try_append_rows_skips_when_not_connected(es_ctx, es_session) -> None:
    connector = LiveNangoConnectorService(get_settings(), es_session)
    status = await try_append_rows(connector, es_ctx, "sheet-1", [["a"]], tab="Test Tab")
    assert status == "skipped-not-connected"


async def test_try_append_rows_ok_when_connected(es_ctx, es_session, mocked_sheets_transport) -> None:
    connector = await _connected_sheets_service(es_ctx, es_session)
    status = await try_append_rows(connector, es_ctx, "sheet-1", [["a"]], tab="Test Tab")
    assert status == "ok"


# ── workflow-level: Pipeline & Carrier Performance Reporting's own
#    POST /{item_id}/export-to-sheet (verticals/es/workflows/pipeline_reporting/
#    router.py) — the ONLY ES workflow with a Sheets write-back. It's per-item
#    and manual (a broker explicitly asks for the export), unlike the MGA-era
#    design's page-level bulk "export every item" button — there is no bulk
#    equivalent here, so no test asserts one. ──


async def _enqueue_pipeline_report(es_session, es_ctx, *, report_id: str, period: str) -> str:
    payload = PipelineReportPayload(report_id=report_id, period=period)
    out_dto = OutputPackageDTO(
        submission_id=period,
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload=payload.model_dump(),
    )
    item = await DefaultReviewQueueService().enqueue(
        es_session, es_ctx, out_dto, PIPELINE_REPORTING_WORKFLOW
    )
    return item.id


async def test_export_to_sheet_404s_for_unknown_item(es_ctx, es_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await export_to_sheet("does-not-exist", es_ctx, es_session)
    assert exc_info.value.status_code == 404


async def test_export_to_sheet_skips_without_sheet_id(es_ctx, es_session) -> None:
    item_id = await _enqueue_pipeline_report(es_session, es_ctx, report_id="RPT-1", period="Q1 2027")
    out = await export_to_sheet(item_id, es_ctx, es_session)
    assert out.status == "skipped-no-sheet-id"


async def test_export_to_sheet_ok_when_connected(es_ctx, es_session) -> None:
    """CONNECTORS_MODE is forced to "mock" for this whole file (fixture above)
    — a real, connected sheet_id is enough for the route's own build_connector_
    service() call to resolve a (mock) connector and succeed, same precedent
    the old MGA bulk-export tests relied on."""
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-4", status="connected", sheet_id="sheet-report-1",
    )
    item_id = await _enqueue_pipeline_report(es_session, es_ctx, report_id="RPT-2", period="Q2 2027")
    out = await export_to_sheet(item_id, es_ctx, es_session)
    assert out.status == "ok"


async def test_export_to_sheet_ok_over_real_nango_proxy_path(
    es_ctx, es_session, monkeypatch, mocked_sheets_transport,
) -> None:
    """End-to-end proof the route is wired to the REAL Sheets API path, not
    just the mock connector shortcut above: forces CONNECTORS_MODE=live so
    build_connector_service() returns a real LiveNangoConnectorService, which
    then has to satisfy the same exact-path-matched mock transport the
    connector-level tests above use — tab-create, header-write, and append,
    all on this workflow's own "Pipeline Reporting" tab/header."""
    monkeypatch.setenv("CONNECTORS_MODE", "live")
    get_settings.cache_clear()
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-5", status="connected", sheet_id="sheet-1",
    )
    item_id = await _enqueue_pipeline_report(es_session, es_ctx, report_id="RPT-3", period="Q3 2027")

    assert "Pipeline Reporting" not in _EXISTING_TITLES
    out = await export_to_sheet(item_id, es_ctx, es_session)
    assert out.status == "ok"
    assert "Pipeline Reporting" in _EXISTING_TITLES
    get_settings.cache_clear()


# ── PATCH /connections/{provider}/sheet-id (Integrations page) ──


async def test_set_sheet_id_rejects_non_sheets_provider(es_ctx, es_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await set_sheet_id(
            "google-mail", SheetIdRequest(sheet_id="abc"), es_ctx, es_session, get_settings()
        )
    assert exc_info.value.status_code == 400


async def test_set_sheet_id_requires_connected_first(es_ctx, es_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await set_sheet_id(
            "google-sheet", SheetIdRequest(sheet_id="abc"), es_ctx, es_session, get_settings()
        )
    assert exc_info.value.status_code == 409


async def test_set_sheet_id_rejects_blank_value(es_ctx, es_session) -> None:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-6", status="connected",
    )
    with pytest.raises(HTTPException) as exc_info:
        await set_sheet_id(
            "google-sheet", SheetIdRequest(sheet_id="   "), es_ctx, es_session, get_settings()
        )
    assert exc_info.value.status_code == 400


async def test_set_sheet_id_persists_when_connected(es_ctx, es_session) -> None:
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-7", status="connected",
    )
    out = await set_sheet_id(
        "google-sheet", SheetIdRequest(sheet_id=" real-sheet-xyz "),
        es_ctx, es_session, get_settings(),
    )
    assert out.sheet_id == "real-sheet-xyz"

    resolved = await resolve_sheet_id(es_session, es_ctx.tenant_id, get_settings())
    assert resolved == "real-sheet-xyz"


async def test_set_sheet_id_extracts_id_from_pasted_url(es_ctx, es_session) -> None:
    """A tenant naturally pastes the full browser URL, not the bare ID buried
    inside it — the route must store just the ID, never the raw URL, or every
    write-back call would break against a malformed Sheets proxy path."""
    await upsert_connection(
        es_session, es_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-8", status="connected",
    )
    url = "https://docs.google.com/spreadsheets/d/1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM/edit?gid=0#gid=0"
    out = await set_sheet_id(
        "google-sheet", SheetIdRequest(sheet_id=url), es_ctx, es_session, get_settings(),
    )
    assert out.sheet_id == "1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM"
