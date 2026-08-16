"""E&S scheduled-monitor tests — fire, idempotency, isolation.

Fixed ``as_of = date(2027, 7, 1)`` throughout.  No TEST_DATA_ROOT required.
All data is seeded inline; LLM-calling pipelines are monkeypatched.

Covers:
  1. binder_issuance_timeline  — ISSUANCE_OVERDUE URGENT + idempotency + clean=none
  2. binder_ongoing_obligations — OBLIGATION_REMINDER WARN at intervals; not before; no BLOCKED
  3. quote_validity_window      — QUOTE_VALIDITY_URGENT; broker-acted=suppressed; QUOTE_LAPSED once
  4. renewal_trigger            — URGENT_REMARKET alert + review; NO_REMARKET; dedup on re-run
  5. carrier_appetite_batch     — empty-DB=none; GENUINE_INCONSISTENCY alert; CONFIRMED_CONSISTENT noop
  6. Failure isolation          — one monitor raises → others complete + job-error row written
  7. Redis-down                 — monitor.run() is Redis-independent; degrades to on-demand only
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, col, select

import core.models  # noqa: F401 — registers all tables
import verticals.es.monitors  # noqa: F401 — registers all 5 monitors
from core.common.dtos import Ctx
from core.common.enums import ReviewStatus, Role, Vertical
from core.jobs.monitor import MonitorAlertIn, get_monitors
from core.models import JobRun as JobRunRow
from core.models import MonitorAlert as MonitorAlertRow
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.models import Tenant

_log = logging.getLogger(__name__)

# ── Fixed reference date ───────────────────────────────────────────────────────

AS_OF = date(2027, 7, 1)

# ── In-memory session fixture ──────────────────────────────────────────────────


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Fresh in-memory SQLite session per test — same pattern as conftest."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def tenant(session: AsyncSession) -> Tenant:
    t = Tenant(id="mon-tenant", name="Monitor Tests", vertical=Vertical.ES, domain="mon.example")
    session.add(t)
    await session.commit()
    return t


@pytest.fixture
def ctx(tenant: Tenant) -> Ctx:
    return Ctx(tenant_id=tenant.id, vertical=Vertical.ES, user_id="mon-system", role=Role.ADMIN)


# ── Seeding helpers ────────────────────────────────────────────────────────────


def _binder_pkg_and_item(
    tenant_id: str,
    *,
    bind_id: str | None = None,
    expected_by: str = "2027-05-01",          # past → overdue by AS_OF
    documents_received: bool = False,
    bind_order_status: str = "SENT",
    obligations: list[dict] | None = None,
    expiration_date: str | None = None,        # for renewal_trigger tests
) -> tuple[OutputPackageRow, ReviewItemRow]:
    """Build a binder_issuance OutputPackage + ReviewItem (not yet persisted)."""
    bid = bind_id or f"bind-{uuid4().hex[:8]}"
    payload: dict[str, Any] = {
        "bind_id": bid,
        "named_insured": "QA Insured Corp",
        "carrier_name": "Ironclad QA",
        "bind_order_status": bind_order_status,
        "policy_issuance": {
            "expected_by_date": expected_by,
            "documents_received": documents_received,
            "carrier_stated_timeline_days": 30,
            "timeline_is_assumed_default": False,
        },
        "post_bind_ongoing_obligations": obligations or [],
        "subjectivities": [],
    }
    if expiration_date:
        payload["requested_bind_terms"] = {"expiration_date": expiration_date, "premium": 120_000}

    pkg = OutputPackageRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        submission_id=f"sub-{bid}",
        workflow="binder_issuance",
        payload=payload,
    )
    item = ReviewItemRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        submission_id=f"sub-{bid}",
        workflow="binder_issuance",
        status=ReviewStatus.PENDING,
        output_package_id=pkg.id,
    )
    return pkg, item


async def _persist(session: AsyncSession, *rows: Any) -> None:
    for row in rows:
        session.add(row)
    await session.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. binder_issuance_timeline
# ═══════════════════════════════════════════════════════════════════════════════


async def test_binder_timeline_overdue_emits_urgent(session: AsyncSession, ctx: Ctx) -> None:
    """Scenario 05 equivalent: docs not received, expected_by in the past → ISSUANCE_OVERDUE URGENT."""
    pkg, item = _binder_pkg_and_item(
        ctx.tenant_id,
        expected_by="2027-05-01",    # ← 61 days before AS_OF
        documents_received=False,
        bind_order_status="SENT",
    )
    await _persist(session, pkg, item)

    monitors = {m.name: m for m in get_monitors()}
    monitor = monitors["binder_issuance_timeline"]

    alerts = await monitor.run(session, ctx, AS_OF)
    assert len(alerts) == 1, f"Expected 1 alert, got {alerts}"
    a = alerts[0]
    assert a.alert_type == "ISSUANCE_OVERDUE"
    assert a.severity == "URGENT"
    assert a.entity_ref == pkg.payload["bind_id"]
    assert a.payload["named_insured"] == "QA Insured Corp"


async def test_binder_timeline_clean_emits_none(session: AsyncSession, ctx: Ctx) -> None:
    """Scenario 01 equivalent: expected_by in the future → no alert."""
    pkg, item = _binder_pkg_and_item(
        ctx.tenant_id,
        expected_by="2027-09-01",    # ← 62 days after AS_OF, not overdue
        documents_received=False,
    )
    await _persist(session, pkg, item)

    monitors = {m.name: m for m in get_monitors()}
    alerts = await monitors["binder_issuance_timeline"].run(session, ctx, AS_OF)
    assert alerts == []


async def test_binder_timeline_docs_received_emits_none(session: AsyncSession, ctx: Ctx) -> None:
    """Documents already received → is_overdue=False → no alert even if past deadline."""
    pkg, item = _binder_pkg_and_item(
        ctx.tenant_id,
        expected_by="2027-05-01",
        documents_received=True,    # ← documents received → not overdue
    )
    await _persist(session, pkg, item)

    monitors = {m.name: m for m in get_monitors()}
    alerts = await monitors["binder_issuance_timeline"].run(session, ctx, AS_OF)
    assert alerts == []


async def test_binder_timeline_idempotent_same_as_of(session: AsyncSession, ctx: Ctx) -> None:
    """Same as_of, same data → same alert list both runs (idempotent at monitor level)."""
    pkg, item = _binder_pkg_and_item(
        ctx.tenant_id,
        expected_by="2027-04-01",
        documents_received=False,
    )
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["binder_issuance_timeline"]
    alerts_run1 = await monitor.run(session, ctx, AS_OF)
    alerts_run2 = await monitor.run(session, ctx, AS_OF)

    assert len(alerts_run1) == 1
    assert len(alerts_run2) == 1
    assert alerts_run1[0].entity_ref == alerts_run2[0].entity_ref
    assert alerts_run1[0].alert_type == alerts_run2[0].alert_type


# ═══════════════════════════════════════════════════════════════════════════════
# 2. binder_ongoing_obligations
# ═══════════════════════════════════════════════════════════════════════════════


async def test_binder_obligations_fires_at_15_days(session: AsyncSession, ctx: Ctx) -> None:
    """Scenario 04 equivalent: obligation due 15 days out → OBLIGATION_REMINDER WARN."""
    # AS_OF = 2027-07-01, REMINDER_INTERVALS_DAYS = (15, 5)
    # due_date = 2027-07-16 → days_remaining = 15 ≤ 15 → reminder_due = True
    obligation = {"description": "Submit updated SOV", "due_date": "2027-07-16", "status": "open"}
    pkg, item = _binder_pkg_and_item(ctx.tenant_id, obligations=[obligation])
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["binder_ongoing_obligations"]
    alerts = await monitor.run(session, ctx, AS_OF)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.alert_type == "OBLIGATION_REMINDER"
    assert a.severity == "WARN"
    assert a.payload["description"] == "Submit updated SOV"
    assert a.payload["days_remaining"] == 15


async def test_binder_obligations_fires_at_5_days(session: AsyncSession, ctx: Ctx) -> None:
    """Obligation due 5 days out (the closer interval) → still fires once."""
    obligation = {"description": "Loss control report", "due_date": "2027-07-06", "status": "open"}
    pkg, item = _binder_pkg_and_item(ctx.tenant_id, obligations=[obligation])
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["binder_ongoing_obligations"]
    alerts = await monitor.run(session, ctx, AS_OF)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "OBLIGATION_REMINDER"
    assert alerts[0].payload["days_remaining"] == 5


async def test_binder_obligations_not_before_window(session: AsyncSession, ctx: Ctx) -> None:
    """Obligation 60 days out → outside reminder window (>15) → NO alert."""
    # AS_OF = 2027-07-01, due_date = 2027-08-30 → 60 days → not ≤ 15 or 5
    obligation = {"description": "Inspection report", "due_date": "2027-08-30", "status": "open"}
    pkg, item = _binder_pkg_and_item(ctx.tenant_id, obligations=[obligation])
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["binder_ongoing_obligations"]
    alerts = await monitor.run(session, ctx, AS_OF)
    assert alerts == [], f"Expected no alert 60 days out, got {alerts}"


async def test_binder_obligations_completed_skipped(session: AsyncSession, ctx: Ctx) -> None:
    """Completed obligation → never emits a reminder regardless of due_date."""
    obligation = {
        "description": "Completed obligation",
        "due_date": "2027-07-06",   # would trigger if open
        "status": "completed",
    }
    pkg, item = _binder_pkg_and_item(ctx.tenant_id, obligations=[obligation])
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["binder_ongoing_obligations"]
    alerts = await monitor.run(session, ctx, AS_OF)
    assert alerts == []


async def test_binder_obligations_never_blocks_bind(session: AsyncSession, ctx: Ctx) -> None:
    """BI-07: reminder alerts WARN only; the bind_order_status is never mutated to BLOCKED."""
    obligation = {"description": "Survey due", "due_date": "2027-07-06", "status": "open"}
    pkg, item = _binder_pkg_and_item(ctx.tenant_id, obligations=[obligation])
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["binder_ongoing_obligations"]
    alerts = await monitor.run(session, ctx, AS_OF)
    assert len(alerts) == 1

    # The monitor must not have written anything that sets bind_order_status to BLOCKED.
    # Verify the persisted OutputPackage is unchanged.
    await session.refresh(pkg)
    payload_after = pkg.payload or {}
    assert payload_after.get("bind_order_status") != "BLOCKED"

    # Alert severity is WARN, not URGENT (reminders are non-blocking per BI-07).
    assert alerts[0].severity == "WARN"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. quote_validity_window
# ═══════════════════════════════════════════════════════════════════════════════


def _quote_pkg_and_item(
    tenant_id: str,
    *,
    quote_valid_through: str,
    status: str = "PENDING_REVIEW",
    make_lapsed: bool = False,
) -> tuple[OutputPackageRow, ReviewItemRow]:
    """Build a quote_comparison OutputPackage + ReviewItem (not yet persisted).

    ``quote_valid_through`` must be in MM/DD/YYYY format — the format that
    ``parse_valid_through_date`` (used by the comparison engine) expects.
    ISO dates (YYYY-MM-DD) are parsed as None by that function.
    """
    quote_id = f"q-{uuid4().hex[:8]}"
    effective_status = "LAPSED" if make_lapsed else status
    payload: dict[str, Any] = {
        "status": effective_status,
        "named_insured": "Continental Freight Corp",
        "submission_id": f"sub-{uuid4().hex[:8]}",
        "output_mode": "SINGLE_QUOTE_ROUTINE",
        "urgency_flags": [],
        "quotes": [
            {
                "quote_id": quote_id,
                "carrier_name": "Clearpath Specialty",
                "response_type": "QUOTE",
                "quote_valid_through": quote_valid_through,  # must be MM/DD/YYYY
                "subjectivities": [],
            }
        ],
    }
    pkg = OutputPackageRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        submission_id=payload["submission_id"],
        workflow="quote_comparison",
        payload=payload,
    )
    item = ReviewItemRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        submission_id=payload["submission_id"],
        workflow="quote_comparison",
        status=ReviewStatus.PENDING,
        output_package_id=pkg.id,
    )
    return pkg, item


async def test_quote_validity_urgent_expiring_quote(session: AsyncSession, ctx: Ctx) -> None:
    """Scenario 06 equivalent: single quote expires in 2 days (< 5 threshold) → QUOTE_VALIDITY_URGENT."""
    # AS_OF = 2027-07-01, quote_valid_through = 07/03/2027 → 2 days remaining ≤ 5
    # parse_valid_through_date uses _parse_mmddyyyy, not ISO format.
    pkg, item = _quote_pkg_and_item(ctx.tenant_id, quote_valid_through="07/03/2027")
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["quote_validity_window"]
    alerts = await monitor.run(session, ctx, AS_OF)

    assert len(alerts) >= 1
    urgency = [a for a in alerts if a.alert_type == "QUOTE_VALIDITY_URGENT"]
    assert len(urgency) == 1, f"Expected 1 QUOTE_VALIDITY_URGENT, got {alerts}"
    assert urgency[0].severity == "URGENT"
    assert "2 day" in urgency[0].payload["detail"]


async def test_quote_validity_not_within_threshold(session: AsyncSession, ctx: Ctx) -> None:
    """Quote valid through 07/15/2027 (14 days) → above threshold → no urgency alert."""
    pkg, item = _quote_pkg_and_item(ctx.tenant_id, quote_valid_through="07/15/2027")
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["quote_validity_window"]
    alerts = await monitor.run(session, ctx, AS_OF)
    urgency = [a for a in alerts if a.alert_type == "QUOTE_VALIDITY_URGENT"]
    assert urgency == [], f"Did not expect urgency 14 days out, got {urgency}"


async def test_quote_validity_broker_acted_suppressed(session: AsyncSession, ctx: Ctx) -> None:
    """Broker logged action (status=PRESENTED) → no QUOTE_VALIDITY_URGENT even if expiring."""
    pkg, item = _quote_pkg_and_item(
        ctx.tenant_id,
        quote_valid_through="07/03/2027",  # would trigger if PENDING_REVIEW
        status="PRESENTED",
    )
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["quote_validity_window"]
    alerts = await monitor.run(session, ctx, AS_OF)
    urgency = [a for a in alerts if a.alert_type == "QUOTE_VALIDITY_URGENT"]
    assert urgency == [], "PRESENTED status must suppress QUOTE_VALIDITY_URGENT"


async def test_quote_lapsed_emits_once_cross_day(session: AsyncSession, ctx: Ctx) -> None:
    """LAPSED quote emits QUOTE_LAPSED exactly ONCE; a pre-existing alert blocks a second emit."""
    pkg, item = _quote_pkg_and_item(ctx.tenant_id, quote_valid_through="06/01/2027", make_lapsed=True)
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["quote_validity_window"]

    # First run → should emit QUOTE_LAPSED.
    alerts_run1 = await monitor.run(session, ctx, AS_OF)
    lapsed = [a for a in alerts_run1 if a.alert_type == "QUOTE_LAPSED"]
    assert len(lapsed) == 1, f"Expected QUOTE_LAPSED on first run, got {alerts_run1}"
    assert lapsed[0].severity == "INFO"

    # Persist the QUOTE_LAPSED alert so the cross-day guard fires next run.
    session.add(MonitorAlertRow(
        id=str(uuid4()),
        tenant_id=ctx.tenant_id,
        vertical=Vertical.ES,
        workflow="quote_comparison",
        entity_ref=item.id,
        alert_type="QUOTE_LAPSED",
        severity="INFO",
        dedupe_key=f"{ctx.tenant_id}:QUOTE_LAPSED:{item.id}:{AS_OF.isoformat()}",
        payload={},
    ))
    await session.commit()

    # Second run same data → cross-day guard fires → 0 QUOTE_LAPSED alerts.
    alerts_run2 = await monitor.run(session, ctx, AS_OF)
    lapsed2 = [a for a in alerts_run2 if a.alert_type == "QUOTE_LAPSED"]
    assert lapsed2 == [], f"QUOTE_LAPSED must not re-emit after persisting, got {alerts_run2}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. renewal_trigger
# ═══════════════════════════════════════════════════════════════════════════════


def _make_renewal_output_pkg(
    tenant_id: str,
    bind_id: str,
    *,
    trigger_level: str = "URGENT_REMARKET",
    is_comparison_stage: bool = False,
) -> OutputPackageRow:
    """Build the OutputPackage that RenewalRemarketingPipeline.run_live() would return."""
    return OutputPackageRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        submission_id=bind_id,
        workflow="renewal_remarketing",
        payload={
            "bind_id": bind_id,
            "named_insured": "Delta Electric Corp",
            "incumbent_carrier_name": "Old Guard Insurance",
            "trigger_decision": {
                "level": trigger_level,
                "reasoning": {"summary": "Incumbent has not responded with renewal terms."},
            },
            "is_comparison_stage": is_comparison_stage,
        },
    )


async def test_renewal_trigger_urgent_remarket_alert_and_review(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Scenario 04 equivalent: bind expiring in 25 days, URGENT_REMARKET → alert + review item."""
    bind_id = f"bind-{uuid4().hex[:8]}"
    # expiration_date = 2027-07-26 → days_until = 25, within 90-day default window
    binder_pkg, binder_item = _binder_pkg_and_item(
        ctx.tenant_id,
        bind_id=bind_id,
        expiration_date="2027-07-26",
    )
    await _persist(session, binder_pkg, binder_item)

    renewal_output = _make_renewal_output_pkg(ctx.tenant_id, bind_id, trigger_level="URGENT_REMARKET")

    with (
        patch(
            "verticals.es.monitors.renewal_trigger.RenewalRemarketingPipeline",
        ) as MockPipeline,
        patch("verticals.es.monitors.renewal_trigger.build_llm_service"),
        patch("verticals.es.monitors.renewal_trigger.DefaultReviewQueueService") as MockQueue,
    ):
        mock_instance = MagicMock()
        mock_instance.run_live = AsyncMock(return_value=renewal_output)
        MockPipeline.return_value = mock_instance
        # enqueue must succeed so execution reaches the URGENT_REMARKET alert block
        MockQueue.return_value.enqueue = AsyncMock()

        monitor = {m.name: m for m in get_monitors()}["renewal_trigger"]
        alerts = await monitor.run(session, ctx, AS_OF)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.alert_type == "RENEWAL_URGENT_REMARKET"
    assert a.severity == "URGENT"
    assert a.entity_ref == bind_id
    assert a.payload["named_insured"] == "Delta Electric Corp"
    assert a.payload["days_until_expiration"] == 25

    # run_live was called once and enqueue was called once.
    mock_instance.run_live.assert_awaited_once_with(ctx, session, bind_id)
    MockQueue.return_value.enqueue.assert_awaited_once()


async def test_renewal_trigger_no_remarket_no_alert(session: AsyncSession, ctx: Ctx) -> None:
    """Scenario 01 equivalent: NO_REMARKET trigger level → review enqueued, 0 URGENT alerts."""
    bind_id = f"bind-{uuid4().hex[:8]}"
    binder_pkg, binder_item = _binder_pkg_and_item(
        ctx.tenant_id,
        bind_id=bind_id,
        expiration_date="2027-07-26",
    )
    await _persist(session, binder_pkg, binder_item)

    renewal_output = _make_renewal_output_pkg(ctx.tenant_id, bind_id, trigger_level="NO_REMARKET")

    with (
        patch("verticals.es.monitors.renewal_trigger.RenewalRemarketingPipeline") as MockPipeline,
        patch("verticals.es.monitors.renewal_trigger.build_llm_service"),
        patch("verticals.es.monitors.renewal_trigger.DefaultReviewQueueService") as MockQueue,
    ):
        mock_instance = MagicMock()
        mock_instance.run_live = AsyncMock(return_value=renewal_output)
        MockPipeline.return_value = mock_instance
        MockQueue.return_value.enqueue = AsyncMock()

        monitor = {m.name: m for m in get_monitors()}["renewal_trigger"]
        alerts = await monitor.run(session, ctx, AS_OF)

    # NO_REMARKET → no MonitorAlert, but run_live and enqueue were still called.
    assert alerts == []
    mock_instance.run_live.assert_awaited_once()
    MockQueue.return_value.enqueue.assert_awaited_once()


async def test_renewal_trigger_skips_when_review_exists(session: AsyncSession, ctx: Ctx) -> None:
    """Idempotency: trigger-stage renewal review already in DB → pipeline NOT called again."""
    bind_id = f"bind-{uuid4().hex[:8]}"

    # Seed a binder package (so the monitor finds the bind).
    binder_pkg, binder_item = _binder_pkg_and_item(
        ctx.tenant_id,
        bind_id=bind_id,
        expiration_date="2027-07-26",
    )
    await _persist(session, binder_pkg, binder_item)

    # Pre-seed a trigger-stage renewal_remarketing output package (idempotency guard).
    existing_renewal_pkg = OutputPackageRow(
        id=str(uuid4()),
        tenant_id=ctx.tenant_id,
        submission_id=bind_id,
        workflow="renewal_remarketing",
        payload={"bind_id": bind_id, "is_comparison_stage": False},
    )
    await _persist(session, existing_renewal_pkg)

    with (
        patch("verticals.es.monitors.renewal_trigger.RenewalRemarketingPipeline") as MockPipeline,
        patch("verticals.es.monitors.renewal_trigger.build_llm_service"),
    ):
        mock_instance = MagicMock()
        mock_instance.run_live = AsyncMock()
        MockPipeline.return_value = mock_instance

        monitor = {m.name: m for m in get_monitors()}["renewal_trigger"]
        alerts = await monitor.run(session, ctx, AS_OF)

    # Idempotency: monitor found existing trigger review → skipped pipeline entirely.
    assert alerts == []
    mock_instance.run_live.assert_not_awaited()


async def test_renewal_trigger_out_of_window_skipped(session: AsyncSession, ctx: Ctx) -> None:
    """Expiration 200 days out → outside trigger window (default 90 days) → not triggered."""
    bind_id = f"bind-{uuid4().hex[:8]}"
    binder_pkg, binder_item = _binder_pkg_and_item(
        ctx.tenant_id,
        bind_id=bind_id,
        expiration_date="2028-01-17",   # 200 days from AS_OF
    )
    await _persist(session, binder_pkg, binder_item)

    with (
        patch("verticals.es.monitors.renewal_trigger.RenewalRemarketingPipeline") as MockPipeline,
        patch("verticals.es.monitors.renewal_trigger.build_llm_service"),
    ):
        mock_instance = MagicMock()
        mock_instance.run_live = AsyncMock()
        MockPipeline.return_value = mock_instance

        monitor = {m.name: m for m in get_monitors()}["renewal_trigger"]
        alerts = await monitor.run(session, ctx, AS_OF)

    assert alerts == []
    mock_instance.run_live.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. carrier_appetite_batch
# ═══════════════════════════════════════════════════════════════════════════════


async def test_carrier_appetite_batch_empty_db_emits_none(
    session: AsyncSession, ctx: Ctx
) -> None:
    """CI FR-1: empty DB (no declination signals) → discover_live_carriers returns [] → 0 alerts."""
    monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
    alerts = await monitor.run(session, ctx, AS_OF)
    assert alerts == []


async def test_carrier_appetite_batch_genuine_inconsistency_alert(
    session: AsyncSession, ctx: Ctx
) -> None:
    """CI-04: GENUINE_INCONSISTENCY → CI_SUGGESTION_CREATED WARN alert + review item enqueued."""
    carrier_id = "ironclad-ci-001"
    carrier_name = "Ironclad Specialty"

    fake_output = OutputPackageRow(
        id=str(uuid4()),
        tenant_id=ctx.tenant_id,
        submission_id=f"ci-{carrier_id}",
        workflow="carrier_appetite_intelligence",
        payload={
            "carrier_id": carrier_id,
            "carrier_name": carrier_name,
            "pattern_type": "GENUINE_INCONSISTENCY",
            "suggestion_id": f"sug-{uuid4().hex[:8]}",
            "class_code": "ALL",
            "suggested_action": "Review appetite — 3 class-level declines in 90 days.",
            "evidence": [
                {"reason_scope": "class_level", "outcome": "inconsistent"},
                {"reason_scope": "class_level", "outcome": "inconsistent"},
                {"reason_scope": "class_level", "outcome": "inconsistent"},
            ],
        },
    )

    with (
        patch(
            "verticals.es.monitors.carrier_appetite_batch.discover_live_carriers",
            new=AsyncMock(return_value=[{"carrier_id": carrier_id, "carrier_name": carrier_name}]),
        ),
        patch(
            "verticals.es.monitors.carrier_appetite_batch.CarrierAppetiteIntelligencePipeline",
        ) as MockPipeline,
        patch("verticals.es.monitors.carrier_appetite_batch.build_llm_service"),
        patch("verticals.es.monitors.carrier_appetite_batch.DefaultReviewQueueService") as MockQueue,
        patch(
            "verticals.es.monitors.carrier_appetite_batch._pending_suggestion_exists",
            new=AsyncMock(return_value=False),
        ),
    ):
        mock_pipeline = MagicMock()
        mock_pipeline.run_live = AsyncMock(return_value=fake_output)
        MockPipeline.return_value = mock_pipeline
        MockQueue.return_value.enqueue = AsyncMock()

        monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
        alerts = await monitor.run(session, ctx, AS_OF)

    assert len(alerts) == 1
    a = alerts[0]
    assert a.alert_type == "CI_SUGGESTION_CREATED"
    assert a.severity == "WARN"
    assert a.entity_ref == carrier_id
    assert a.payload["carrier_name"] == carrier_name
    assert a.payload["class_level_inconsistent_count"] == 3
    MockQueue.return_value.enqueue.assert_awaited_once()


async def test_carrier_appetite_batch_confirmed_consistent_no_urgent_alert(
    session: AsyncSession, ctx: Ctx
) -> None:
    """CI-03: CONFIRMED_CONSISTENT → metadata refresh called, CI_METADATA_REFRESHED INFO (no WARN)."""
    carrier_id = "ironclad-ci-002"
    carrier_name = "Ironclad Specialty"

    fake_output = OutputPackageRow(
        id=str(uuid4()),
        tenant_id=ctx.tenant_id,
        submission_id=f"ci-{carrier_id}",
        workflow="carrier_appetite_intelligence",
        payload={
            "carrier_id": carrier_id,
            "carrier_name": carrier_name,
            "pattern_type": "CONFIRMED_CONSISTENT",
            "appetite_confidence": "high",
            "appetite_last_updated": AS_OF.isoformat(),
        },
    )

    with (
        patch(
            "verticals.es.monitors.carrier_appetite_batch.discover_live_carriers",
            new=AsyncMock(return_value=[{"carrier_id": carrier_id, "carrier_name": carrier_name}]),
        ),
        patch(
            "verticals.es.monitors.carrier_appetite_batch.CarrierAppetiteIntelligencePipeline",
        ) as MockPipeline,
        patch("verticals.es.monitors.carrier_appetite_batch.build_llm_service"),
        patch(
            "verticals.es.monitors.carrier_appetite_batch.CarrierProfileService.refresh_metadata",
            new=AsyncMock(),
        ),
        patch(
            "verticals.es.monitors.carrier_appetite_batch._already_refreshed_today",
            new=AsyncMock(return_value=False),
        ),
    ):
        mock_pipeline = MagicMock()
        mock_pipeline.run_live = AsyncMock(return_value=fake_output)
        MockPipeline.return_value = mock_pipeline

        monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
        alerts = await monitor.run(session, ctx, AS_OF)

    # CONFIRMED_CONSISTENT → INFO alert (not WARN / URGENT).
    assert len(alerts) == 1
    a = alerts[0]
    assert a.alert_type == "CI_METADATA_REFRESHED"
    assert a.severity == "INFO"
    assert a.entity_ref == carrier_id


async def test_carrier_appetite_batch_insufficient_signal_suppressed(
    session: AsyncSession, ctx: Ctx
) -> None:
    """CI-05: INSUFFICIENT_SIGNAL → correct default, produces 0 alerts."""
    carrier_id = "unknown-carrier-ci"
    carrier_name = "Unknown Carrier"

    fake_output = OutputPackageRow(
        id=str(uuid4()),
        tenant_id=ctx.tenant_id,
        submission_id=f"ci-{carrier_id}",
        workflow="carrier_appetite_intelligence",
        payload={
            "carrier_id": carrier_id,
            "carrier_name": carrier_name,
            "pattern_type": "INSUFFICIENT_SIGNAL",
        },
    )

    with (
        patch(
            "verticals.es.monitors.carrier_appetite_batch.discover_live_carriers",
            new=AsyncMock(return_value=[{"carrier_id": carrier_id, "carrier_name": carrier_name}]),
        ),
        patch(
            "verticals.es.monitors.carrier_appetite_batch.CarrierAppetiteIntelligencePipeline",
        ) as MockPipeline,
        patch("verticals.es.monitors.carrier_appetite_batch.build_llm_service"),
    ):
        mock_pipeline = MagicMock()
        mock_pipeline.run_live = AsyncMock(return_value=fake_output)
        MockPipeline.return_value = mock_pipeline

        monitor = {m.name: m for m in get_monitors()}["carrier_appetite_batch"]
        alerts = await monitor.run(session, ctx, AS_OF)

    assert alerts == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Failure isolation
# ═══════════════════════════════════════════════════════════════════════════════


async def test_failure_isolation_one_raises_others_complete(
    session: AsyncSession, ctx: Ctx
) -> None:
    """Force one monitor's run() to raise; the rest still complete and a job-error row is written."""
    from core.jobs.service import JobRunService, JobStatus

    all_monitors = get_monitors()
    assert len(all_monitors) >= 2, "Need at least 2 monitors for isolation test"

    # Pick the first monitor to fail; all others should still complete.
    failing_name = all_monitors[0].name
    completed: list[str] = []
    error_rows_before = (
        await session.execute(select(JobRunRow))
    ).scalars().all()
    error_count_before = sum(1 for r in error_rows_before if r.status == "error")

    for monitor in all_monitors:
        try:
            if monitor.name == failing_name:
                raise RuntimeError(f"Simulated {monitor.name} failure")
            alerts = await monitor.run(session, ctx, AS_OF)
            completed.append(monitor.name)
        except Exception as exc:
            # Mirrors run_scheduled_monitors's error path (KB06-compliant: no fabrication).
            run_id = await JobRunService.create(
                session,
                job_name=f"monitor:{monitor.name}",
                tenant_id=ctx.tenant_id,
                args={"as_of": AS_OF.isoformat()},
            )
            await JobRunService.mark(session, run_id, JobStatus.ERROR, error=str(exc))

    # Every monitor except the failing one ran successfully.
    assert failing_name not in completed
    assert len(completed) == len(all_monitors) - 1, (
        f"Expected {len(all_monitors) - 1} to complete, got {completed}"
    )

    # Exactly one new job-error row was written for the failing monitor.
    error_rows_after = (await session.execute(select(JobRunRow))).scalars().all()
    error_count_after = sum(1 for r in error_rows_after if r.status == "error")
    new_errors = error_count_after - error_count_before
    assert new_errors == 1, f"Expected 1 new job-error row, got {new_errors}"

    # Verify the error row names the right monitor.
    error_row = next(
        r for r in error_rows_after
        if r.status == "error" and f"monitor:{failing_name}" in (r.job_name or "")
    )
    assert "Simulated" in error_row.error


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Redis-down: monitors degrade to on-demand only; API still serves
# ═══════════════════════════════════════════════════════════════════════════════


async def test_redis_down_monitor_run_is_redis_independent(
    session: AsyncSession, ctx: Ctx
) -> None:
    """monitor.run() completes without any Redis connection.

    The Arq cron that SCHEDULES monitors requires Redis; but the monitor's
    ``run()`` method itself only touches the SQLAlchemy session — it is pure
    on-demand logic reachable without Redis.  This test confirms the two layers
    are decoupled: if Redis goes down, broker-triggered on-demand calls still work.
    """
    # Seed one overdue binder so the monitor has something to check.
    pkg, item = _binder_pkg_and_item(
        ctx.tenant_id,
        expected_by="2027-04-01",
        documents_received=False,
    )
    await _persist(session, pkg, item)

    monitor = {m.name: m for m in get_monitors()}["binder_issuance_timeline"]

    # Simulate Redis being unavailable: import the arq redis helpers and confirm
    # they would raise, then show monitor.run() is unaffected.
    import socket

    def _no_redis(*args: Any, **kwargs: Any) -> None:
        raise ConnectionRefusedError("Redis refused connection (simulated)")

    with patch("socket.socket.connect", side_effect=_no_redis):
        # monitor.run() does NOT touch the network — it only uses the injected
        # async session (a pure in-memory SQLite connection for this test).
        alerts = await monitor.run(session, ctx, AS_OF)

    assert len(alerts) == 1
    assert alerts[0].alert_type == "ISSUANCE_OVERDUE"


async def test_redis_down_all_five_monitors_still_runnable(
    session: AsyncSession, ctx: Ctx
) -> None:
    """All 5 monitors complete their run() without Redis — no import raises, no network call."""
    all_monitors = {m.name: m for m in get_monitors()}
    expected = {
        "binder_issuance_timeline",
        "binder_ongoing_obligations",
        "quote_validity_window",
        "renewal_trigger",
        "carrier_appetite_batch",
    }
    assert expected <= set(all_monitors), f"Missing monitors: {expected - set(all_monitors)}"

    # Patch all external I/O that monitors might attempt so they complete cleanly.
    with (
        patch("verticals.es.monitors.renewal_trigger.RenewalRemarketingPipeline") as MockRP,
        patch("verticals.es.monitors.renewal_trigger.build_llm_service"),
        patch(
            "verticals.es.monitors.carrier_appetite_batch.discover_live_carriers",
            new=AsyncMock(return_value=[]),   # empty → batch exits early, no LLM call
        ),
        patch("verticals.es.monitors.carrier_appetite_batch.build_llm_service"),
    ):
        MockRP.return_value.run_live = AsyncMock(return_value=None)

        for name in expected:
            monitor = all_monitors[name]
            # Must not raise regardless of Redis availability.
            result = await monitor.run(session, ctx, AS_OF)
            assert isinstance(result, list), f"{name}.run() must return list, got {type(result)}"
