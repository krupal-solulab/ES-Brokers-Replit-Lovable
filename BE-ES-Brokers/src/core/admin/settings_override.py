"""In-process cache of ``PlatformSetting`` overrides (Admin Panel, AP-04).

Integration-point decision (PRD §7/§8 leaves this open for engineering):
several call sites for the six admin-editable settings sit deep inside a
workflow's ``decide()``/``extract()`` step, which only receives ``ctx`` —
no ``AsyncSession`` — because ``core.common``'s ``WorkflowPipeline`` Protocol
is frozen and not something this feature may change. Threading a session
into every such call site would mean editing that Protocol's shape across
every vertical, which is out of scope.

Instead, overrides live in a plain process-wide dict, hydrated from the
``platform_setting`` table once at app startup (see ``main.py``'s lifespan)
and kept in sync by every admin write (``core/admin/service.py``). Reads are
therefore synchronous and dependency-free — safe to call from anywhere,
including inside a pipeline's pure compute steps — while writes still persist
to the DB so an override survives a restart.
"""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.models import PlatformSetting

T = TypeVar("T", int, float, str)

# The only six keys this cache ever holds (PRD §5.4) — kept here as the single
# source of truth for what "a platform setting" means to the backend.
SETTING_KEYS: frozenset[str] = frozenset(
    {
        "junior_premium_cap",
        "connectors_mode",
        "nango_inbox_query",
        "quote_rank_price_weight",
        "quote_rank_subjectivity_penalty",
        "carrier_appetite_min_total_outcomes",
    }
)

_overrides: dict[tuple[str, str], str] = {}


def get_effective_setting(tenant_id: str, key: str, default: T) -> T:
    """``default`` should already be the caller's resolved env/Settings value.
    Returns the tenant's admin override if one exists, cast to ``type(default)``,
    else ``default`` unchanged."""
    raw = _overrides.get((tenant_id, key))
    if raw is None:
        return default
    return type(default)(raw)


def has_override(tenant_id: str, key: str) -> bool:
    return (tenant_id, key) in _overrides


def set_override(tenant_id: str, key: str, value: str) -> None:
    _overrides[(tenant_id, key)] = value


def clear_override(tenant_id: str, key: str) -> None:
    _overrides.pop((tenant_id, key), None)


async def hydrate_overrides(session: AsyncSession) -> None:
    """Load every persisted override into the cache. Called once at app
    startup so a process restart doesn't lose admin-set overrides."""
    rows = (await session.execute(select(PlatformSetting))).scalars().all()
    for row in rows:
        _overrides[(row.tenant_id, row.key)] = row.value
