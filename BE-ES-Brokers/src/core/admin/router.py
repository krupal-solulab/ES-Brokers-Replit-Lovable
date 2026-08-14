"""Routes under ``/api/core/admin`` — tenant/user management, live platform
settings, an audit viewer, and the Overview landing screen. Every route is
gated by ``require_role(Role.ADMIN)`` — no frontend guard is ever the sole
protection (PRD §5.8), and every query stays scoped to the caller's own
``ctx.tenant_id`` — this PRD never returns another tenant's data.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.admin.schema import (
    AuditEntryOut,
    OverviewOut,
    SettingOut,
    SettingUpdate,
    TenantOut,
    TenantUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from core.admin.service import (
    DuplicateEmailError,
    InvalidRoleError,
    InvalidSettingError,
    UserNotFoundError,
    clear_setting,
    create_user,
    get_overview,
    get_tenant,
    list_settings,
    list_users,
    save_setting,
    update_tenant,
    update_user,
)
from core.admin.service import query_audit as _query_audit
from core.auth import require_role
from core.common.dtos import Ctx
from core.common.enums import Role
from core.db import get_session

router = APIRouter(prefix="/admin", tags=["core:admin"])

AdminCtxDep = Annotated[Ctx, Depends(require_role(Role.ADMIN))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/overview")
async def overview(ctx: AdminCtxDep, session: SessionDep) -> OverviewOut:
    return await get_overview(session, ctx)


# ── Tenant (AP-02) ────────────────────────────────────────


@router.get("/tenant")
async def read_tenant(ctx: AdminCtxDep, session: SessionDep) -> TenantOut:
    return await get_tenant(session, ctx)


@router.patch("/tenant")
async def patch_tenant(body: TenantUpdate, ctx: AdminCtxDep, session: SessionDep) -> TenantOut:
    try:
        return await update_tenant(
            session, ctx, name=body.name, junior_premium_cap=body.junior_premium_cap
        )
    except InvalidSettingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


# ── Users (AP-03) ─────────────────────────────────────────


@router.get("/users")
async def read_users(ctx: AdminCtxDep, session: SessionDep) -> list[UserOut]:
    return await list_users(session, ctx)


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def post_user(body: UserCreate, ctx: AdminCtxDep, session: SessionDep) -> UserOut:
    try:
        return await create_user(
            session, ctx, email=body.email, name=body.name, role=body.role
        )
    except DuplicateEmailError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidRoleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: str, body: UserUpdate, ctx: AdminCtxDep, session: SessionDep
) -> UserOut:
    try:
        return await update_user(session, ctx, user_id, role=body.role, name=body.name)
    except UserNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidRoleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


# ── Settings (AP-04) ──────────────────────────────────────


@router.get("/settings")
async def read_settings(ctx: AdminCtxDep, session: SessionDep) -> list[SettingOut]:
    return await list_settings(session, ctx)


@router.patch("/settings/{key}")
async def patch_setting(
    key: str, body: SettingUpdate, ctx: AdminCtxDep, session: SessionDep
) -> SettingOut:
    try:
        return await save_setting(session, ctx, key, body.value)
    except InvalidSettingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.delete("/settings/{key}")
async def delete_setting(key: str, ctx: AdminCtxDep, session: SessionDep) -> SettingOut:
    try:
        return await clear_setting(session, ctx, key)
    except InvalidSettingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


# ── Audit (AP-06) ─────────────────────────────────────────


@router.get("/audit")
async def read_audit(
    ctx: AdminCtxDep,
    session: SessionDep,
    workflow: str | None = None,
    actor: str | None = None,
    limit: int = 50,
) -> list[AuditEntryOut]:
    return await _query_audit(session, ctx, workflow=workflow, actor=actor, limit=limit)
