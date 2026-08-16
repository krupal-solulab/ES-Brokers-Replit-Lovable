"""Routes under ``/api/core/monitors``.

GET  /alerts            — list MonitorAlert rows for the caller's tenant
                          (any authenticated role; tenant-scoped).
POST /alerts/{id}/dismiss — resolve an alert (SENIOR or ADMIN only).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.auth import require_roles
from core.common.dtos import Ctx
from core.common.enums import Role
from core.config import get_settings
from core.db import get_session
from core.jobs.monitor import MonitorAlertIn, get_monitor
from core.models import MonitorAlert as MonitorAlertRow, Tenant
from core.tenancy.dependencies import get_ctx

router = APIRouter(prefix="/monitors", tags=["core:monitors"])

# Any authenticated tenant user may list alerts.
CtxDep = Annotated[Ctx, Depends(get_ctx)]
# Dismissing / dev-triggering is a consequential action — SENIOR or ADMIN only.
SeniorCtxDep = Annotated[Ctx, Depends(require_roles(Role.SENIOR, Role.ADMIN))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Valid names for the dev manual-trigger endpoint.
_ALLOWED_MONITORS: frozenset[str] = frozenset({
    "binder_issuance_timeline",
    "binder_ongoing_obligations",
    "quote_validity_window",
    "renewal_trigger",
    "carrier_appetite_batch",
})


# ── Output schema ─────────────────────────────────────────────────────────────

class MonitorAlertOut(BaseModel):
    id: str
    tenant_id: str
    vertical: str
    workflow: str
    entity_ref: str
    alert_type: str
    severity: str
    dedupe_key: str
    payload: dict[str, Any]
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None


def _row_to_out(row: MonitorAlertRow) -> MonitorAlertOut:
    return MonitorAlertOut(
        id=row.id,
        tenant_id=row.tenant_id,
        vertical=str(row.vertical),
        workflow=row.workflow,
        entity_ref=row.entity_ref,
        alert_type=row.alert_type,
        severity=row.severity,
        dedupe_key=row.dedupe_key,
        payload=row.payload or {},
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        resolved_by=row.resolved_by,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{name}/run")
async def run_monitor_for_date(
    name: str,
    ctx: SeniorCtxDep,
    session: SessionDep,
    as_of: date = Query(..., description="Date to run the monitor for (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """Dev/QA trigger: run one scheduled monitor for a specific date.

    Only available when ``APP_ENV != production``.  Returns the MonitorAlert rows
    produced (or already persisted for that date — idempotent).
    Guard: SENIOR or ADMIN role only.
    """
    if get_settings().app_env == "production":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    if name not in _ALLOWED_MONITORS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown monitor '{name}'; valid names: {sorted(_ALLOWED_MONITORS)}",
        )

    monitor = get_monitor(name)
    if monitor is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"monitor '{name}' not registered — ensure the app imported all monitor modules",
        )

    as_of_str = as_of.isoformat()

    # ── Idempotency: return existing rows for this monitor+date without re-running ──
    existing = list(
        (
            await session.execute(
                select(MonitorAlertRow).where(
                    col(MonitorAlertRow.tenant_id) == ctx.tenant_id,
                    col(MonitorAlertRow.workflow) == monitor.workflow,
                    col(MonitorAlertRow.dedupe_key).like(f"%:{as_of_str}"),
                )
            )
        )
        .scalars()
        .all()
    )
    if existing:
        return {"success": True, "data": [_row_to_out(r) for r in existing], "created": False}

    # ── Resolve tenant vertical (needed to create alert rows) ──────────────────
    tenant_row = (
        await session.execute(select(Tenant).where(col(Tenant.id) == ctx.tenant_id))
    ).scalar_one_or_none()
    if tenant_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")

    # ── Run the monitor ────────────────────────────────────────────────────────
    alert_ins: list[MonitorAlertIn] = await monitor.run(session, ctx, as_of=as_of)

    inserted: list[MonitorAlertRow] = []
    for alert_in in alert_ins:
        dedupe_key = (
            f"{ctx.tenant_id}:{alert_in.alert_type}:{alert_in.entity_ref}:{as_of_str}"
        )
        # Race-safe: skip if a concurrent call already inserted this key.
        already = (
            await session.execute(
                select(MonitorAlertRow).where(
                    col(MonitorAlertRow.dedupe_key) == dedupe_key
                )
            )
        ).scalar_one_or_none()
        if already is not None:
            inserted.append(already)
            continue
        row = MonitorAlertRow(
            tenant_id=ctx.tenant_id,
            vertical=tenant_row.vertical,
            workflow=monitor.workflow,
            entity_ref=alert_in.entity_ref,
            alert_type=alert_in.alert_type,
            severity=alert_in.severity,
            dedupe_key=dedupe_key,
            payload=alert_in.payload,
        )
        session.add(row)
        inserted.append(row)

    await session.commit()
    for row in inserted:
        if row.id:  # skip rows that were already-existing (no id refresh needed)
            await session.refresh(row)

    return {"success": True, "data": [_row_to_out(r) for r in inserted], "created": True}


@router.get("/alerts")
async def list_alerts(
    ctx: CtxDep,
    session: SessionDep,
    workflow: str | None = Query(default=None, description="Filter by workflow name"),
    resolved: bool | None = Query(
        default=None,
        description="true = resolved only, false = open only, omit = all",
    ),
) -> dict[str, Any]:
    """List MonitorAlert rows for the caller's tenant.

    Scoped to ``ctx.tenant_id`` — never leaks another tenant's data.
    """
    stmt = (
        select(MonitorAlertRow)
        .where(col(MonitorAlertRow.tenant_id) == ctx.tenant_id)
        .order_by(col(MonitorAlertRow.created_at).desc())
    )

    if workflow is not None:
        stmt = stmt.where(col(MonitorAlertRow.workflow) == workflow)

    if resolved is True:
        stmt = stmt.where(col(MonitorAlertRow.resolved_at).is_not(None))
    elif resolved is False:
        stmt = stmt.where(col(MonitorAlertRow.resolved_at).is_(None))

    rows = list((await session.execute(stmt)).scalars().all())
    return {"success": True, "data": [_row_to_out(r) for r in rows]}


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    ctx: SeniorCtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    """Resolve (dismiss) a MonitorAlert.

    Sets ``resolved_at`` and ``resolved_by``; the row is never deleted.
    Idempotent — dismissing an already-resolved alert returns the existing row.
    """
    row = (
        await session.execute(
            select(MonitorAlertRow).where(
                col(MonitorAlertRow.id) == alert_id,
                col(MonitorAlertRow.tenant_id) == ctx.tenant_id,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"alert '{alert_id}' not found")

    if row.resolved_at is None:
        row.resolved_at = datetime.now(UTC)
        row.resolved_by = ctx.user_id
        session.add(row)
        await session.commit()
        await session.refresh(row)

    return {"success": True, "data": _row_to_out(row)}
