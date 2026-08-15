"""Routes under ``/api/core/monitors``.

GET  /alerts            — list MonitorAlert rows for the caller's tenant
                          (any authenticated role; tenant-scoped).
POST /alerts/{id}/dismiss — resolve an alert (SENIOR or ADMIN only).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.auth import require_roles
from core.common.dtos import Ctx
from core.common.enums import Role
from core.db import get_session
from core.models import MonitorAlert as MonitorAlertRow
from core.tenancy.dependencies import get_ctx

router = APIRouter(prefix="/monitors", tags=["core:monitors"])

# Any authenticated tenant user may list alerts.
CtxDep = Annotated[Ctx, Depends(get_ctx)]
# Dismissing is a consequential action — SENIOR or ADMIN only.
SeniorCtxDep = Annotated[Ctx, Depends(require_roles(Role.SENIOR, Role.ADMIN))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


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
