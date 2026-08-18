"""Routes under ``/api/core/app-config`` — exposes the raw, env-configured
``CONNECTORS_MODE`` value so the frontend can decide whether to show its own
sample/dummy data. Deliberately reads the global env setting only, never a
per-tenant admin override (``core/admin/settings_override.py``) — this is the
one thing every tenant/role sees identically, straight from ``.env``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from core.common.dtos import Ctx
from core.config import get_settings
from core.data_mode import resolve_data_mode
from core.db import get_session
from core.tenancy.dependencies import get_ctx

router = APIRouter(prefix="/app-config", tags=["core:app-config"])

CtxDep = Annotated[Ctx, Depends(get_ctx)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class AppConfigOut(BaseModel):
    connectors_mode: str


@router.get("")
async def get_app_config(ctx: CtxDep) -> AppConfigOut:
    return AppConfigOut(connectors_mode=get_settings().connectors_mode)


class DataModeOut(BaseModel):
    """Product-wide data mode for the FE banner: mode "static" means every
    screen is serving fixture/deterministic data (never half-live)."""

    mode: str  # "live" | "static"
    reason: str  # "" | "mock_mode" | "connector_disconnected" | "llm_insufficient_quota"


@router.get("/data-mode")
async def get_data_mode(ctx: CtxDep, session: SessionDep) -> DataModeOut:
    result = await resolve_data_mode(session, ctx.tenant_id)
    return DataModeOut(mode=result.mode, reason=result.reason)
