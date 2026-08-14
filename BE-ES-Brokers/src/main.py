"""FastAPI application entry point (Phase 0 skeleton).

Mounts the shared core health route + both (empty) vertical routers. Run with:
    uvicorn main:app --app-dir src --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.admin.router import router as admin_router
from core.admin.settings_override import hydrate_overrides
from core.app_config.router import router as app_config_router
from core.assistant.router import router as assistant_router
from core.auth.router import router as auth_router
from core.dashboard.router import router as dashboard_router
from core.db import async_session_factory
from core.integrations.router import router as integrations_router
from verticals.es.router import router as es_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Warms the Admin Panel's in-process settings-override cache (see
    core/admin/settings_override.py) from the persisted PlatformSetting table,
    so an admin override survives a process restart."""
    async with async_session_factory() as session:
        await hydrate_overrides(session)
    yield


app = FastAPI(title="Insurance OS Backend", version="0.0.0", lifespan=lifespan)

# Dev-only: the Lovable-managed frontends' sandbox dev servers are pinned to
# port 8080 by convention (@lovable.dev/vite-tanstack-config), but Vite falls
# through to the next free port (8081, 8082, ...) when 8080 is already taken
# by another Lovable app running locally at the same time (e.g.
# IndustryAI-Insaurance-ES-Brokers and Admin-ES-Brokers side by side) — so a
# small fixed range is allow-listed here, not just 8080 itself. Header-stub
# auth (Phase 0) means no cookies are involved, so credentials stay disabled.
# `allow_origin_regex` additionally covers Vercel's per-branch/PR preview
# subdomains (e.g. insurance-os-es-broker-fe-98n7.vercel.app), not just one
# fixed hostname.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        *(f"http://localhost:{port}" for port in range(8080, 8090)),
        # The deployed dev/staging frontend (Azure VM, IP-based — no domain yet).
        # A small fixed range, not just 3000, for the same reason as the localhost
        # range above — the frontend falls through to the next free port (3001, 3002,
        # ...) when 3000 is already taken by another run on the same VM.
        *(f"http://57.174.232.34:{port}" for port in range(3000, 3006)),
        # Same VM, served over HTTPS via a nip.io wildcard hostname + reverse proxy.
        "https://broker.57.174.232.34.nip.io",
        "*"
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

core_router = APIRouter(prefix="/api/core", tags=["core"])


@core_router.get("/health")
async def health() -> dict[str, int]:
    """Liveness probe. Phase marker confirms which milestone this build is at."""
    return {"phase": 0}


core_router.include_router(integrations_router)
core_router.include_router(auth_router)
core_router.include_router(assistant_router)
core_router.include_router(dashboard_router)
core_router.include_router(admin_router)
core_router.include_router(app_config_router)

app.include_router(core_router)
app.include_router(es_router)
