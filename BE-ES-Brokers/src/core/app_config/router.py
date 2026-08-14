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

from core.common.dtos import Ctx
from core.config import get_settings
from core.tenancy.dependencies import get_ctx

router = APIRouter(prefix="/app-config", tags=["core:app-config"])

CtxDep = Annotated[Ctx, Depends(get_ctx)]


class AppConfigOut(BaseModel):
    connectors_mode: str


@router.get("")
async def get_app_config(ctx: CtxDep) -> AppConfigOut:
    return AppConfigOut(connectors_mode=get_settings().connectors_mode)
