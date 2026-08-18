"""Product-wide data-mode resolver (live vs static fixture data).

One shared decision for the entire product — connectors, LLM drafting, and the
FE banner all consult the same resolver so the app is never half-live /
half-static. ``static`` means: serve the existing per-workflow fixture path
(``MockConnectorService`` + ``fixtures/loader.py``) and the deterministic LLM
output. Nothing is fabricated — static output comes from the fixtures/engine
(Deterministic Logic Boundary).

Triggers (checked in order):
1. ``mock_mode`` — effective ``connectors_mode`` is "mock" (env default or the
   per-tenant admin override, AP-04).
2. ``llm_insufficient_quota`` — a live OpenAI call recently failed with an
   insufficient_quota / 429 billing error (short-lived process-local flag set
   by ``core.llm.service``; TTL below).
3. ``connector_disconnected`` — connectors_mode is "live" but ANY of the
   registered ingest/writeback connectors (mail, sheets, drive, slack) has no
   active Nango connection. Live mode with everything connected resolves to
   ``live``.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.admin.settings_override import get_effective_setting
from core.config import get_settings

# ---------------------------------------------------------------------------
# Reason (c): short-lived "LLM out of quota" flag. Process-local by design —
# it exists to stop hammering a billing-failed provider and to flip the whole
# app to static output for a while, not to be a durable record.
# ---------------------------------------------------------------------------

_LLM_QUOTA_FLAG_TTL_SECONDS = 300.0
_llm_quota_flagged_at: float | None = None


def note_llm_quota_error() -> None:
    """Called by the LLM layer when OpenAI reports insufficient_quota / a 429
    billing error — flips the whole product to static data for the TTL."""
    global _llm_quota_flagged_at
    _llm_quota_flagged_at = time.monotonic()


def clear_llm_quota_flag() -> None:
    """Test/ops helper — forget a previously noted quota error."""
    global _llm_quota_flagged_at
    _llm_quota_flagged_at = None


def llm_quota_active() -> bool:
    if _llm_quota_flagged_at is None:
        return False
    if time.monotonic() - _llm_quota_flagged_at > _LLM_QUOTA_FLAG_TTL_SECONDS:
        clear_llm_quota_flag()
        return False
    return True


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------


def effective_connectors_mode(tenant_id: str | None) -> str:
    """Env default, overridable per tenant by an admin (AP-04)."""
    mode = get_settings().connectors_mode
    if tenant_id is not None:
        mode = get_effective_setting(tenant_id, "connectors_mode", mode)
    return str(mode)


@dataclass(frozen=True)
class DataMode:
    mode: str  # "live" | "static"
    reason: str  # "" | "mock_mode" | "connector_disconnected" | "llm_insufficient_quota"


def resolve_data_mode_sync(tenant_id: str | None) -> DataMode | None:
    """The synchronous-only checks (a) and (c). Returns None when the answer
    depends on the DB connection check — callers without a session may treat
    None as live-so-far (the connector wrapper still falls back at call time
    if the connection turns out to be missing)."""
    if effective_connectors_mode(tenant_id) == "mock":
        return DataMode("static", "mock_mode")
    if llm_quota_active():
        return DataMode("static", "llm_insufficient_quota")
    return None


# Short per-tenant cache of the connection check so the per-request middleware
# doesn't add a DB lookup to every single API call.
_CONN_CHECK_TTL_SECONDS = 15.0
_conn_check_cache: dict[str, tuple[float, bool]] = {}


def invalidate_connection_cache(tenant_id: str | None = None) -> None:
    """Called after a connect/disconnect so the mode flips immediately."""
    if tenant_id is None:
        _conn_check_cache.clear()
    else:
        _conn_check_cache.pop(tenant_id, None)


async def resolve_data_mode(session: AsyncSession, tenant_id: str) -> DataMode:
    """The one product-wide answer: ("live"|"static", reason)."""
    sync_answer = resolve_data_mode_sync(tenant_id)
    if sync_answer is not None:
        return sync_answer

    # (b) live mode, but are ALL connectors the ingest/writeback paths use
    # connected? Any missing one flips the whole product to static — a single
    # combined answer is cached per tenant (never per-connector) so the mode
    # can never disagree between connectors within the TTL.
    cached = _conn_check_cache.get(tenant_id)
    now = time.monotonic()
    if cached is not None and now - cached[0] <= _CONN_CHECK_TTL_SECONDS:
        connected = cached[1]
    else:
        from core.integrations.repository import get_connection  # avoids import cycle

        settings = get_settings()
        providers = (
            settings.nango_integration_mail,
            settings.nango_integration_sheet,
            settings.nango_integration_drive,
            settings.nango_integration_slack,
        )
        connected = True
        for provider in providers:
            conn = await get_connection(session, tenant_id, provider)
            if not (conn is not None and conn.status == "connected" and conn.nango_connection_id):
                connected = False
                break
        _conn_check_cache[tenant_id] = (now, connected)
    if not connected:
        return DataMode("static", "connector_disconnected")
    return DataMode("live", "")


# ---------------------------------------------------------------------------
# Request-scoped current mode: set once per API request by the middleware in
# main.py, consulted synchronously by the connector and LLM factories so every
# service built during that request agrees — never half-live/half-static.
# Outside a request (monitors/jobs), it is unset and the factories fall back
# to the synchronous checks (mock mode + quota flag).
# ---------------------------------------------------------------------------

_current_data_mode: ContextVar[DataMode | None] = ContextVar("current_data_mode", default=None)


def set_current_data_mode(mode: DataMode | None):
    return _current_data_mode.set(mode)


def get_current_data_mode() -> DataMode | None:
    return _current_data_mode.get()
