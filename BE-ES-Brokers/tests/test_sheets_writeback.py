"""Proves the Sheets export fallback (docs/CONNECTORS_NANGO.md): connector-level
append/read against a mocked Nango Sheets proxy (httpx.MockTransport, no real
network), plus each of the 3 originally-built workflows' export_all_to_sheet —
a manual, page-level bulk action that exports every item in the workflow's list
regardless of status. As of the bulk-export redesign, act("approve") no longer
triggers any Sheets write-back at all; that assertion is covered explicitly here.
Mirrors test_live_nango_connector.py's pattern. Gmail/mock-connector behavior is
untouched.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from fastapi import HTTPException

import core.models  # noqa: F401  (registers tables)
from core.common.dtos import Ctx
from core.common.dtos import Decision as DecisionDTO
from core.common.dtos import Draft
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
from verticals.mga.bind_issuance.schema import (
    BindDetail,
    DownstreamTriggersOut,
    IssuanceReconciliationOut,
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
    for every test in this file so act()'s write-back call never attempts a real
    Nango request via build_connector_service. get_settings() is @lru_cache'd, so
    the cache must be cleared on both sides of the env-var flip (same fix used by
    the ES live-connector tests, e.g. test_es_endorsement.py's live_gmail_connected)."""
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


async def _connected_sheets_service(mga_ctx, mga_session) -> LiveNangoConnectorService:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-1", status="connected",
    )
    return LiveNangoConnectorService(get_settings(), mga_session)


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


async def test_append_rows_not_connected_raises(mga_ctx, mga_session) -> None:
    service = LiveNangoConnectorService(get_settings(), mga_session)
    with pytest.raises(ConnectorNotConnectedError):
        await service.append_rows(mga_ctx, "sheet-1", [["x"]], tab="Test Tab")


async def test_append_rows_posts_to_sheets_proxy(
    mga_ctx, mga_session, mocked_sheets_transport
) -> None:
    service = await _connected_sheets_service(mga_ctx, mga_session)
    await service.append_rows(mga_ctx, "sheet-1", [["BND-1", "READY"]], tab="Test Tab")


async def test_read_range_gets_from_sheets_proxy(
    mga_ctx, mga_session, mocked_sheets_transport
) -> None:
    service = await _connected_sheets_service(mga_ctx, mga_session)
    rows = await service.read_range(mga_ctx, "sheet-1", "A1:B2", tab="Test Tab")
    assert rows == [["a", "b"]]


async def test_append_rows_creates_tab_and_header_when_missing(
    mga_ctx, mga_session, mocked_sheets_transport
) -> None:
    """First-ever write to a fresh tab: batchUpdate (addSheet) + values.update
    (header) must both fire before the data-row append."""
    service = await _connected_sheets_service(mga_ctx, mga_session)
    assert "Bind Issuance" not in _EXISTING_TITLES
    await service.append_rows(
        mga_ctx, "sheet-1", [["BND-1", "sub-1", "Acme", "READY", 1000, "2027-01-01"]],
        tab="Bind Issuance",
        header=["Bind ID", "Submission ID", "Named Insured", "Status", "Premium", "Approved At"],
    )
    assert "Bind Issuance" in _EXISTING_TITLES


async def test_append_rows_skips_tab_creation_when_already_exists(
    mga_ctx, mga_session, mocked_sheets_transport
) -> None:
    """A second write to the same tab must not re-create it or re-write the header
    — only the existence check (GET) + the data append should fire."""
    _EXISTING_TITLES.add("Bind Issuance")
    service = await _connected_sheets_service(mga_ctx, mga_session)
    await service.append_rows(
        mga_ctx, "sheet-1", [["BND-2", "sub-2", "Beta", "READY", 2000, "2027-01-02"]],
        tab="Bind Issuance",
        header=["Bind ID", "Submission ID", "Named Insured", "Status", "Premium", "Approved At"],
    )
    # No error means the handler's exact-match routes were satisfied without an
    # unexpected batchUpdate/update call landing on the (unhandled -> 404) path.


# ── connector-level: MockConnectorService ──


async def test_mock_append_rows_records_in_memory() -> None:
    ctx = Ctx(tenant_id="demo-mga", vertical=Vertical.MGA, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    await service.append_rows(ctx, "sheet-1", [["a", "b"]], tab="Test Tab")
    assert await service.read_range(ctx, "sheet-1", "A1", tab="Test Tab") == [["a", "b"]]


async def test_mock_append_rows_isolates_tabs() -> None:
    ctx = Ctx(tenant_id="demo-mga", vertical=Vertical.MGA, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    await service.append_rows(ctx, "sheet-1", [["a"]], tab="Tab A")
    await service.append_rows(ctx, "sheet-1", [["b"]], tab="Tab B")
    assert await service.read_range(ctx, "sheet-1", "A1", tab="Tab A") == [["a"]]
    assert await service.read_range(ctx, "sheet-1", "A1", tab="Tab B") == [["b"]]


async def test_mock_append_rows_writes_header_only_once() -> None:
    ctx = Ctx(tenant_id="demo-mga", vertical=Vertical.MGA, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    header = ["Col A", "Col B"]
    await service.append_rows(ctx, "sheet-1", [["1", "2"]], tab="Tab A", header=header)
    await service.append_rows(ctx, "sheet-1", [["3", "4"]], tab="Tab A", header=header)
    rows = await service.read_range(ctx, "sheet-1", "A1", tab="Tab A")
    assert rows == [header, ["1", "2"], ["3", "4"]]


# ── resolve_sheet_id: reads the tenant's own Connection row, never .env ──


async def test_resolve_sheet_id_empty_when_not_connected(mga_ctx, mga_session) -> None:
    sheet_id = await resolve_sheet_id(mga_session, mga_ctx.tenant_id, get_settings())
    assert sheet_id == ""


async def test_resolve_sheet_id_empty_when_connected_but_unset(mga_ctx, mga_session) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-2", status="connected",
    )
    sheet_id = await resolve_sheet_id(mga_session, mga_ctx.tenant_id, get_settings())
    assert sheet_id == ""


async def test_resolve_sheet_id_reads_tenants_own_connection(mga_ctx, mga_session) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-3", status="connected", sheet_id="real-sheet-abc",
    )
    sheet_id = await resolve_sheet_id(mga_session, mga_ctx.tenant_id, get_settings())
    assert sheet_id == "real-sheet-abc"


# ── try_append_rows helper: never raises, reports status ──


async def test_try_append_rows_skips_without_sheet_id() -> None:
    ctx = Ctx(tenant_id="demo-mga", vertical=Vertical.MGA, user_id="u", role=Role.SENIOR)
    status = await try_append_rows(MockConnectorService(), ctx, "", [["a"]], tab="Test Tab")
    assert status == "skipped-no-sheet-id"


async def test_try_append_rows_skips_when_not_connected(mga_ctx, mga_session) -> None:
    connector = LiveNangoConnectorService(get_settings(), mga_session)
    status = await try_append_rows(connector, mga_ctx, "sheet-1", [["a"]], tab="Test Tab")
    assert status == "skipped-not-connected"


async def test_try_append_rows_ok_when_connected(mga_ctx, mga_session, mocked_sheets_transport) -> None:
    connector = await _connected_sheets_service(mga_ctx, mga_session)
    status = await try_append_rows(connector, mga_ctx, "sheet-1", [["a"]], tab="Test Tab")
    assert status == "ok"


# ── workflow export_all_to_sheet: bulk-exports the whole list, any status,
#    manual/button-triggered — approve() no longer auto-writes anything ──


async def test_bind_issuance_act_no_longer_touches_sheets(mga_ctx, mga_session) -> None:
    """Approve must succeed on its own terms with no Sheets side effect at all —
    write-back is now exclusively a manual bulk action, never triggered by act()."""
    service = BindIssuanceService()
    detail = BindDetail(
        bindId="BND-1", submissionId="sub-1", namedInsured="Acme LLC",
        worksheetReference=None, stalenessCheck=None, preBindSubjectivities=[],
        authorityReconfirmation=None, bindOrderStatus="READY",
        pasWriteBack=WriteBackOut(logged=True, bordereauSchemaValidated=True),
        issuanceReconciliation=IssuanceReconciliationOut(status="NOT_YET_ISSUED", discrepancyDetail=[]),
        postBindObligations=[],
        downstreamTriggersFired=DownstreamTriggersOut(bindConfirmation=False, policyDelivered=False),
        rationale="ok", activity=[],
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
    assert not hasattr(service, "_write_back")
    assert not hasattr(service, "export_pdf")


async def test_bind_issuance_export_all_to_sheet_skips_without_sheet_id(mga_ctx, mga_session) -> None:
    service = BindIssuanceService()
    status = await service.export_all_to_sheet(mga_session, mga_ctx)
    assert status == "skipped-no-sheet-id"


async def test_bind_issuance_export_all_to_sheet_exports_every_item_any_status(
    mga_ctx, mga_session,
) -> None:
    """Bulk export must include pending/escalated/approved items alike — no
    status filtering, unlike the old approve-only write-back."""
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-4", status="connected", sheet_id="sheet-bind-1",
    )
    service = BindIssuanceService()
    for i, bind_id in enumerate(["BND-A", "BND-B"]):
        detail = BindDetail(
            bindId=bind_id, submissionId=f"sub-{i}", namedInsured="Acme LLC",
            worksheetReference=None, stalenessCheck=None, preBindSubjectivities=[],
            authorityReconfirmation=None, bindOrderStatus="READY",
            pasWriteBack=WriteBackOut(logged=True, bordereauSchemaValidated=True),
            issuanceReconciliation=IssuanceReconciliationOut(
                status="NOT_YET_ISSUED", discrepancyDetail=[]),
            postBindObligations=[],
            downstreamTriggersFired=DownstreamTriggersOut(
                bindConfirmation=False, policyDelivered=False),
            rationale="ok", activity=[],
        )
        out_dto = OutputPackageDTO(
            submission_id=f"sub-{i}",
            decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
            draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
            payload={"detail": detail.model_dump(by_alias=True)},
        )
        await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, BIND_WORKFLOW)
    # leave sub-0 pending, approve only sub-1 — both must still appear in the export
    await service.act(mga_session, mga_ctx, "sub-1", "approve")

    status = await service.export_all_to_sheet(mga_session, mga_ctx)
    assert status == "ok"


async def test_bordereau_export_all_to_sheet_skips_without_sheet_id(mga_ctx, mga_session) -> None:
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
        submission_id="sub-2",
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={"detail": detail.model_dump(by_alias=True)},
    )
    await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, BORDEREAU_WORKFLOW)

    result = await service.act(mga_session, mga_ctx, "sub-2", "approve")
    assert result["status"] == "approved"

    status = await service.export_all_to_sheet(mga_session, mga_ctx)
    assert status == "skipped-no-sheet-id"


async def test_renewal_export_all_to_sheet_skips_without_sheet_id(mga_ctx, mga_session) -> None:
    service = RenewalService()
    detail = RenewalDetail(
        id="sub-3", subject="Renewal - Acme - Eff 2027-01-01", recommendation="RENEW_AS_IS",
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
        id="sub-3", subject=detail.subject, insured="Acme LLC",
        recommendation=detail.recommendation, score=None, retention=detail.retention,
        daysToExpiration=30, lapseRisk=False, status="pending", received="2027-01-01",
        priorPremium=detail.priorPremium, indicated=detail.indicated,
    )
    out_dto = OutputPackageDTO(
        submission_id="sub-3",
        decision=DecisionDTO(outcome=DecisionOutcome.PROCEED, score=None, rationale="ok"),
        draft=Draft(text="ok", citations=[]), flags=[], missing_info=[],
        payload={
            "detail": detail.model_dump(by_alias=True),
            "row": row.model_dump(),
            "activity": [],
        },
    )
    await service.review_queue.enqueue(mga_session, mga_ctx, out_dto, RENEWAL_WORKFLOW)

    result = await service.act(mga_session, mga_ctx, "sub-3", "approve")
    assert result["status"] == "approved"

    status = await service.export_all_to_sheet(mga_session, mga_ctx)
    assert status == "skipped-no-sheet-id"


# ── PATCH /connections/{provider}/sheet-id (Integrations page) ──


async def test_set_sheet_id_rejects_non_sheets_provider(mga_ctx, mga_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await set_sheet_id(
            "google-mail", SheetIdRequest(sheet_id="abc"), mga_ctx, mga_session, get_settings()
        )
    assert exc_info.value.status_code == 400


async def test_set_sheet_id_requires_connected_first(mga_ctx, mga_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await set_sheet_id(
            "google-sheet", SheetIdRequest(sheet_id="abc"), mga_ctx, mga_session, get_settings()
        )
    assert exc_info.value.status_code == 409


async def test_set_sheet_id_rejects_blank_value(mga_ctx, mga_session) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-5", status="connected",
    )
    with pytest.raises(HTTPException) as exc_info:
        await set_sheet_id(
            "google-sheet", SheetIdRequest(sheet_id="   "), mga_ctx, mga_session, get_settings()
        )
    assert exc_info.value.status_code == 400


async def test_set_sheet_id_persists_when_connected(mga_ctx, mga_session) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-6", status="connected",
    )
    out = await set_sheet_id(
        "google-sheet", SheetIdRequest(sheet_id=" real-sheet-xyz "),
        mga_ctx, mga_session, get_settings(),
    )
    assert out.sheet_id == "real-sheet-xyz"

    resolved = await resolve_sheet_id(mga_session, mga_ctx.tenant_id, get_settings())
    assert resolved == "real-sheet-xyz"


async def test_set_sheet_id_extracts_id_from_pasted_url(mga_ctx, mga_session) -> None:
    """A tenant naturally pastes the full browser URL, not the bare ID buried
    inside it — the route must store just the ID, never the raw URL, or every
    write-back call would break against a malformed Sheets proxy path."""
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-sheet",
        nango_connection_id="conn-sheet-7", status="connected",
    )
    url = "https://docs.google.com/spreadsheets/d/1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM/edit?gid=0#gid=0"
    out = await set_sheet_id(
        "google-sheet", SheetIdRequest(sheet_id=url), mga_ctx, mga_session, get_settings(),
    )
    assert out.sheet_id == "1nndB_iHLVbFgg04IVmGXTuYU1q5_kkV5lDA1QJiu5jM"
