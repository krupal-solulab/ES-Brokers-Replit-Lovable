"""Proves the Drive-upload fallback (docs/CONNECTORS_NANGO.md): connector-level
put_file against a mocked Nango Drive proxy (httpx.MockTransport, no real
network), the PDF generators, and each of the 3 originally-built workflows'
export_all_to_drive — a manual, page-level bulk action that uploads one PDF
covering every item in the workflow's list regardless of status. As of the
bulk-export redesign, act("approve") no longer triggers any Drive upload at
all; that assertion is covered explicitly here. Mirrors
test_sheets_writeback.py's pattern.
"""

from __future__ import annotations

import io
import json
from collections.abc import AsyncGenerator

import httpx
import pytest
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

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
from core.ingestion.pdf_export import render_bulk_summary_pdf, render_summary_pdf
from core.ingestion.writeback import extract_folder_id, resolve_drive_folder_id, try_put_file
from core.integrations.repository import upsert_connection
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
    for every test in this file so export_pdf's upload call never attempts a real
    Nango request via build_connector_service."""
    monkeypatch.setenv("CONNECTORS_MODE", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _drive_handler(request: httpx.Request) -> httpx.Response:
    """Exact-path-matched, per the lesson from Sheets: a loose match is exactly
    what let a wrong path ship to production undetected. Uploads use a DIFFERENT
    host path than metadata-only calls (upload/drive/v3/files, not drive/v3/files)."""
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


async def _connected_drive_service(mga_ctx, mga_session) -> LiveNangoConnectorService:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-drive",
        nango_connection_id="conn-drive-1", status="connected",
    )
    return LiveNangoConnectorService(get_settings(), mga_session)


# ── extract_folder_id: a pasted URL must never reach the Drive proxy verbatim ──


def test_extract_folder_id_from_bare_id() -> None:
    assert extract_folder_id("1AbCdEfGhIjKlMnOpQrS") == "1AbCdEfGhIjKlMnOpQrS"


def test_extract_folder_id_from_full_url() -> None:
    url = "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrS?usp=sharing"
    assert extract_folder_id(url) == "1AbCdEfGhIjKlMnOpQrS"


def test_extract_folder_id_from_shared_drive_url() -> None:
    url = "https://drive.google.com/drive/u/0/folders/1AbCdEfGhIjKlMnOpQrS"
    assert extract_folder_id(url) == "1AbCdEfGhIjKlMnOpQrS"


# ── render_summary_pdf: proves a real, readable PDF ──


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


# ── render_bulk_summary_pdf: one page per item, used by the new bulk action ──


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


async def test_put_file_not_connected_raises(mga_ctx, mga_session) -> None:
    service = LiveNangoConnectorService(get_settings(), mga_session)
    with pytest.raises(ConnectorNotConnectedError):
        await service.put_file(mga_ctx, "", "test.pdf", b"data", "application/pdf")


async def test_put_file_creates_metadata_then_uploads_content(
    mga_ctx, mga_session, mocked_drive_transport
) -> None:
    service = await _connected_drive_service(mga_ctx, mga_session)
    file_id = await service.put_file(
        mga_ctx, "folder-1", "bind-BND-1.pdf", b"%PDF-fake-content", "application/pdf"
    )
    assert file_id == "drive-file-1"


async def test_put_file_omits_parents_when_no_folder_id(
    mga_ctx, mga_session, mocked_drive_transport
) -> None:
    service = await _connected_drive_service(mga_ctx, mga_session)
    file_id = await service.put_file(mga_ctx, "", "bind-BND-1.pdf", b"data", "application/pdf")
    assert file_id == "drive-file-1"


# ── connector-level: MockConnectorService ──


async def test_mock_put_file_records_in_memory() -> None:
    ctx = Ctx(tenant_id="demo-mga", vertical=Vertical.MGA, user_id="u", role=Role.SENIOR)
    service = MockConnectorService()
    file_id = await service.put_file(ctx, "folder-1", "test.pdf", b"data", "application/pdf")
    assert file_id
    assert service._files == [("folder-1", "test.pdf", b"data", "application/pdf")]


# ── resolve_drive_folder_id: empty is a valid "root Drive" value, not a skip ──


async def test_resolve_drive_folder_id_empty_when_not_connected(mga_ctx, mga_session) -> None:
    folder_id = await resolve_drive_folder_id(mga_session, mga_ctx.tenant_id, get_settings())
    assert folder_id == ""


async def test_resolve_drive_folder_id_reads_tenants_own_connection(mga_ctx, mga_session) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-drive",
        nango_connection_id="conn-drive-2", status="connected", folder_id="real-folder-abc",
    )
    folder_id = await resolve_drive_folder_id(mga_session, mga_ctx.tenant_id, get_settings())
    assert folder_id == "real-folder-abc"


# ── try_put_file helper: never raises, reports status ──


async def test_try_put_file_skips_when_not_connected(mga_ctx, mga_session) -> None:
    connector = LiveNangoConnectorService(get_settings(), mga_session)
    status = await try_put_file(connector, mga_ctx, "", "test.pdf", b"data", "application/pdf")
    assert status == "skipped-not-connected"


async def test_try_put_file_ok_when_connected(mga_ctx, mga_session, mocked_drive_transport) -> None:
    connector = await _connected_drive_service(mga_ctx, mga_session)
    status = await try_put_file(connector, mga_ctx, "folder-1", "test.pdf", b"data", "application/pdf")
    assert status == "ok"


async def test_try_put_file_ok_with_no_folder_id(mga_ctx, mga_session, mocked_drive_transport) -> None:
    """Empty folder id is NOT a skip condition for Drive, unlike Sheets' empty
    sheet_id — it just means upload to the tenant's Drive root."""
    connector = await _connected_drive_service(mga_ctx, mga_session)
    status = await try_put_file(connector, mga_ctx, "", "test.pdf", b"data", "application/pdf")
    assert status == "ok"


# ── workflow export_all_to_drive: bulk-uploads one PDF covering the whole list,
#    any status, manual/button-triggered — approve() never touches Drive ──


async def test_bind_issuance_act_no_longer_touches_drive(mga_ctx, mga_session) -> None:
    """Approve must succeed on its own terms with no Drive side effect at all —
    upload is now exclusively a manual bulk action, never triggered by act()."""
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
    assert not hasattr(service, "export_pdf")


async def test_bind_issuance_export_all_to_drive_skips_when_not_connected(
    mga_ctx, mga_session, monkeypatch,
) -> None:
    """MockConnectorService always "succeeds" (no connection concept), so this
    forces CONNECTORS_MODE=live with no seeded Connection row — the real path a
    genuinely unconnected tenant hits — to prove the guard works end to end."""
    monkeypatch.setenv("CONNECTORS_MODE", "live")
    get_settings.cache_clear()
    service = BindIssuanceService()
    status = await service.export_all_to_drive(mga_session, mga_ctx)
    assert status == "skipped-not-connected"
    get_settings.cache_clear()


async def test_bind_issuance_export_all_to_drive_covers_every_item_any_status(
    mga_ctx, mga_session,
) -> None:
    """Bulk upload must include pending/escalated/approved items alike — no
    status filtering, unlike the old approve-only per-item upload."""
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-drive",
        nango_connection_id="conn-drive-3", status="connected",
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
    await service.act(mga_session, mga_ctx, "sub-1", "approve")  # sub-0 stays pending

    status = await service.export_all_to_drive(mga_session, mga_ctx)
    assert status == "ok"


async def test_bordereau_export_all_to_drive_ok_when_connected(mga_ctx, mga_session) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-drive",
        nango_connection_id="conn-drive-4", status="connected",
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

    status = await service.export_all_to_drive(mga_session, mga_ctx)
    assert status == "ok"


async def test_renewal_export_all_to_drive_ok_when_connected(mga_ctx, mga_session) -> None:
    await upsert_connection(
        mga_session, mga_ctx.tenant_id, "google-drive",
        nango_connection_id="conn-drive-5", status="connected",
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

    status = await service.export_all_to_drive(mga_session, mga_ctx)
    assert status == "ok"
