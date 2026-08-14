"""Admin Panel business logic (AP-02..AP-06). Every function is tenant-scoped to
``ctx.tenant_id`` — none of them may be given a way to reach another tenant's rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.admin.schema import (
    AuditEntryOut,
    ConnectionSummaryOut,
    OverviewOut,
    SettingOut,
    TenantOut,
    UserOut,
)
from core.admin.settings_override import (
    SETTING_KEYS,
    clear_override,
    has_override,
    set_override,
)
from core.audit.service import DefaultAuditService
from core.common.dtos import Ctx
from core.common.enums import Role, Vertical
from core.config import get_settings
from core.integrations.repository import list_connections
from core.models import PlatformSetting, Tenant, User


class UserNotFoundError(Exception):
    """Raised when a user id doesn't resolve, or resolves outside the caller's tenant."""


class DuplicateEmailError(Exception):
    """Raised when creating a user whose email already exists for this tenant."""


class InvalidRoleError(Exception):
    """Raised when a role string isn't one of junior/senior/admin."""


class InvalidSettingError(Exception):
    """Raised for an unknown setting key or a value that fails its type/range check."""


@dataclass(frozen=True)
class _SettingDef:
    key: str
    label: str
    description: str
    cast: type


_SETTING_DEFS: list[_SettingDef] = [
    _SettingDef(
        "junior_premium_cap",
        "Junior Premium Cap",
        "Global fallback premium ceiling a junior can approve without escalation — "
        "overridden per-tenant by Tenant Settings' own junior_premium_cap field, if set.",
        float,
    ),
    _SettingDef(
        "connectors_mode",
        "Connectors Mode",
        "Whether every workflow's live-inbox/live-run paths use fixtures (mock) or the "
        "real Nango connectors (live).",
        str,
    ),
    _SettingDef(
        "nango_inbox_query",
        "Nango Inbox Query",
        "Gmail search query used by Market Matching's live-inbox picker.",
        str,
    ),
    _SettingDef(
        "quote_rank_price_weight",
        "Quote Rank Price Weight",
        "Weight applied to price when Quote Comparison ranks carrier quotes.",
        float,
    ),
    _SettingDef(
        "quote_rank_subjectivity_penalty",
        "Quote Rank Subjectivity Penalty",
        "Penalty applied per subjectivity attached to a quote in Quote Comparison.",
        float,
    ),
    _SettingDef(
        "carrier_appetite_min_total_outcomes",
        "Carrier Appetite Min Total Outcomes",
        "Minimum total real declinations from one carrier before Carrier Appetite "
        "Intelligence's pattern judgment fires.",
        int,
    ),
]
_SETTING_DEFS_BY_KEY = {d.key: d for d in _SETTING_DEFS}
assert {d.key for d in _SETTING_DEFS} == SETTING_KEYS  # keep the two lists honest


def _validate_setting_value(key: str, raw_value: str) -> str:
    """Casts/range-checks ``raw_value`` for ``key``; returns the value to persist
    (still a string — ``PlatformSetting.value`` is string-typed by design, §7).
    Raises ``InvalidSettingError`` on a bad key or a value that fails its check."""
    setting_def = _SETTING_DEFS_BY_KEY.get(key)
    if setting_def is None:
        raise InvalidSettingError(f"unknown setting key: {key}")
    if key == "connectors_mode":
        if raw_value not in ("mock", "live"):
            raise InvalidSettingError("connectors_mode must be 'mock' or 'live'")
        return raw_value
    if key == "nango_inbox_query":
        if not raw_value.strip():
            raise InvalidSettingError("nango_inbox_query may not be empty")
        return raw_value
    try:
        parsed = setting_def.cast(raw_value)
    except (TypeError, ValueError) as exc:
        raise InvalidSettingError(f"{key} must be a valid {setting_def.cast.__name__}") from exc
    if parsed < 0:
        raise InvalidSettingError(f"{key} may not be negative")
    return raw_value


# ── Tenant (AP-02) ────────────────────────────────────────


async def get_tenant(session: AsyncSession, ctx: Ctx) -> TenantOut:
    tenant = (
        await session.execute(select(Tenant).where(col(Tenant.id) == ctx.tenant_id))
    ).scalar_one()
    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        vertical=Vertical(tenant.vertical).value,
        junior_premium_cap=tenant.junior_premium_cap,
    )


async def update_tenant(
    session: AsyncSession, ctx: Ctx, *, name: str | None, junior_premium_cap: float | None
) -> TenantOut:
    tenant = (
        await session.execute(select(Tenant).where(col(Tenant.id) == ctx.tenant_id))
    ).scalar_one()
    if name is not None:
        tenant.name = name
    if junior_premium_cap is not None:
        if junior_premium_cap < 0:
            raise InvalidSettingError("junior_premium_cap may not be negative")
        tenant.junior_premium_cap = junior_premium_cap
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return await get_tenant(session, ctx)


# ── Users (AP-03) ─────────────────────────────────────────


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, name=user.name, role=Role(user.role).value,
        created_at=user.created_at,
    )


async def list_users(session: AsyncSession, ctx: Ctx) -> list[UserOut]:
    rows = (
        (await session.execute(select(User).where(col(User.tenant_id) == ctx.tenant_id)))
        .scalars()
        .all()
    )
    return [_user_out(u) for u in rows]


async def create_user(
    session: AsyncSession, ctx: Ctx, *, email: str, name: str | None, role: str
) -> UserOut:
    email = email.strip().lower()
    try:
        role_enum = Role(role)
    except ValueError as exc:
        raise InvalidRoleError(f"invalid role: {role}") from exc

    existing = (
        await session.execute(select(User).where(col(User.email) == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateEmailError(f"a user with email '{email}' already exists")

    user = User(tenant_id=ctx.tenant_id, email=email, name=name, role=role_enum)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_out(user)


async def update_user(
    session: AsyncSession, ctx: Ctx, user_id: str, *, role: str | None, name: str | None
) -> UserOut:
    user = (
        await session.execute(
            select(User).where(col(User.id) == user_id, col(User.tenant_id) == ctx.tenant_id)
        )
    ).scalar_one_or_none()
    if user is None:
        raise UserNotFoundError(f"user '{user_id}' not found for this tenant")
    if role is not None:
        try:
            user.role = Role(role)
        except ValueError as exc:
            raise InvalidRoleError(f"invalid role: {role}") from exc
    if name is not None:
        user.name = name
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_out(user)


# ── Settings (AP-04) ──────────────────────────────────────


async def list_settings(session: AsyncSession, ctx: Ctx) -> list[SettingOut]:
    rows = (
        (
            await session.execute(
                select(PlatformSetting).where(col(PlatformSetting.tenant_id) == ctx.tenant_id)
            )
        )
        .scalars()
        .all()
    )
    overrides_by_key = {r.key: r for r in rows}
    settings = get_settings()
    out: list[SettingOut] = []
    for setting_def in _SETTING_DEFS:
        env_default = str(getattr(settings, setting_def.key))
        override_row = overrides_by_key.get(setting_def.key)
        is_override = has_override(ctx.tenant_id, setting_def.key)
        out.append(
            SettingOut(
                key=setting_def.key,
                label=setting_def.label,
                description=setting_def.description,
                value=override_row.value if override_row is not None else env_default,
                env_default=env_default,
                source="admin_override" if is_override else "env_default",
                updated_at=override_row.updated_at if override_row is not None else None,
                updated_by=override_row.updated_by if override_row is not None else None,
            )
        )
    return out


async def save_setting(
    session: AsyncSession, ctx: Ctx, key: str, value: str
) -> SettingOut:
    clean_value = _validate_setting_value(key, value)
    row = (
        await session.execute(
            select(PlatformSetting).where(
                col(PlatformSetting.tenant_id) == ctx.tenant_id, col(PlatformSetting.key) == key
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = PlatformSetting(
            tenant_id=ctx.tenant_id, key=key, value=clean_value, updated_by=ctx.user_id
        )
    else:
        row.value = clean_value
        row.updated_by = ctx.user_id
        row.updated_at = datetime.now(UTC)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    set_override(ctx.tenant_id, key, clean_value)  # takes effect immediately, no restart
    settings_list = await list_settings(session, ctx)
    return next(s for s in settings_list if s.key == key)


async def clear_setting(session: AsyncSession, ctx: Ctx, key: str) -> SettingOut:
    if key not in SETTING_KEYS:
        raise InvalidSettingError(f"unknown setting key: {key}")
    row = (
        await session.execute(
            select(PlatformSetting).where(
                col(PlatformSetting.tenant_id) == ctx.tenant_id, col(PlatformSetting.key) == key
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()
    clear_override(ctx.tenant_id, key)
    settings_list = await list_settings(session, ctx)
    return next(s for s in settings_list if s.key == key)


# ── Audit (AP-06) ─────────────────────────────────────────


async def query_audit(
    session: AsyncSession,
    ctx: Ctx,
    *,
    workflow: str | None,
    actor: str | None,
    limit: int,
) -> list[AuditEntryOut]:
    filter_: dict[str, Any] = {}
    if workflow:
        filter_["workflow"] = workflow
    if actor:
        filter_["actor"] = actor
    entries = await DefaultAuditService().query(session, ctx, filter_)
    most_recent_first = sorted(entries, key=lambda e: e.at or datetime.min, reverse=True)
    return [
        AuditEntryOut(
            actor=e.actor, who=e.who, what=e.what, workflow=e.workflow, at=e.at,
            detail=e.detail,
        )
        for e in most_recent_first[:limit]
    ]


# ── Overview (landing screen — flow §4 step 3) ────────────


async def get_overview(session: AsyncSession, ctx: Ctx, *, audit_limit: int = 5) -> OverviewOut:
    tenant = await get_tenant(session, ctx)
    connections = await list_connections(session, ctx.tenant_id)
    recent_audit = await query_audit(session, ctx, workflow=None, actor=None, limit=audit_limit)
    return OverviewOut(
        tenant=tenant,
        connections=[
            ConnectionSummaryOut(provider=c.provider, status=c.status) for c in connections
        ],
        recent_audit=recent_audit,
    )
