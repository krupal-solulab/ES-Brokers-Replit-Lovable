"""Admin Panel (AP-01..AP-06) — role gate, tenant/user management, live settings
overrides (no restart), and the cross-workflow audit wrapper. Uses the shared
``mem_session``/``mga_ctx`` fixtures from ``conftest.py``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import core.admin.settings_override as settings_override_module
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
    query_audit,
    save_setting,
    update_tenant,
    update_user,
)
from core.admin.settings_override import get_effective_setting
from core.audit import DefaultAuditService
from core.auth import require_role
from core.common.dtos import AuditEntry, Ctx
from core.common.enums import Role, Vertical
from core.config import get_settings
from core.models import Tenant, User
from core.review_queue import AuthorityError, DefaultReviewQueueService
from core.tenancy.dependencies import get_ctx


@pytest.fixture(autouse=True)
def _clear_override_cache():
    """The settings-override cache is a process-wide dict (by design — see
    settings_override.py's module docstring); reset it so tests don't leak
    overrides into each other."""
    settings_override_module._overrides.clear()
    yield
    settings_override_module._overrides.clear()


def _ctx(tenant_id: str, role: Role) -> Ctx:
    return Ctx(tenant_id=tenant_id, vertical=Vertical.MGA, user_id=f"u-{role.value}", role=role)


# ── AP-01: role guard ─────────────────────────────────────


async def test_require_role_admin_blocks_junior_and_senior(mem_session: AsyncSession) -> None:
    guard = require_role(Role.ADMIN)
    with pytest.raises(HTTPException) as exc:
        await guard(_ctx("demo-mga", Role.JUNIOR))
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await guard(_ctx("demo-mga", Role.SENIOR))
    assert exc.value.status_code == 403


async def test_require_role_admin_allows_admin(mem_session: AsyncSession) -> None:
    guard = require_role(Role.ADMIN)
    ctx = await guard(_ctx("demo-mga", Role.ADMIN))
    assert ctx.role is Role.ADMIN


# ── AP-02: tenant ─────────────────────────────────────────


async def test_get_tenant_returns_real_row(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    out = await get_tenant(mem_session, ctx)
    assert out.id == "demo-mga"
    assert out.junior_premium_cap is None


async def test_tenant_cap_override_blocks_junior_on_next_review_action(
    mem_session: AsyncSession,
) -> None:
    """AP-02's acceptance line: setting a tenant-level cap changes real
    review-queue authority on the very next action, no restart."""
    ctx = _ctx("demo-mga", Role.ADMIN)
    await update_tenant(mem_session, ctx, name=None, junior_premium_cap=75_000)

    junior_ctx = _ctx("demo-mga", Role.JUNIOR)
    from core.common.dtos import Decision, OutputPackage
    from core.common.enums import DecisionOutcome, ReviewAction

    pkg = OutputPackage(decision=Decision(outcome=DecisionOutcome.PROCEED), payload={})
    item = await DefaultReviewQueueService().enqueue(mem_session, junior_ctx, pkg, "wf")
    rq = DefaultReviewQueueService()
    with pytest.raises(AuthorityError):
        await rq.act(mem_session, junior_ctx, item.id, ReviewAction.APPROVE, amount=100_000)
    # still within the new $75k cap
    ok = await rq.act(mem_session, junior_ctx, item.id, ReviewAction.APPROVE, amount=50_000)
    assert ok is not None


async def test_tenant_cap_rejects_negative(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    with pytest.raises(InvalidSettingError):
        await update_tenant(mem_session, ctx, name=None, junior_premium_cap=-1)


# ── AP-03: users ──────────────────────────────────────────


async def test_create_user_is_immediately_loginable(mem_session: AsyncSession) -> None:
    """AP-03's acceptance line: POST /users must reuse login's exact lookup
    shape (User.email) so a new user can log in with no other change."""
    ctx = _ctx("demo-mga", Role.ADMIN)
    created = await create_user(
        mem_session, ctx, email="New.Broker@Example.com", name="New Broker", role="junior"
    )
    from sqlmodel import col, select

    looked_up = (
        await mem_session.execute(select(User).where(col(User.email) == "new.broker@example.com"))
    ).scalar_one_or_none()
    assert looked_up is not None
    assert looked_up.id == created.id
    assert looked_up.role is Role.JUNIOR


async def test_create_user_duplicate_email_rejected(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    await create_user(mem_session, ctx, email="dup@example.com", name="A", role="junior")
    with pytest.raises(DuplicateEmailError):
        await create_user(mem_session, ctx, email="dup@example.com", name="B", role="senior")


async def test_create_user_invalid_role_rejected(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    with pytest.raises(InvalidRoleError):
        await create_user(mem_session, ctx, email="x@example.com", name="X", role="owner")


async def test_update_user_role_round_trips_through_get_ctx(mem_session: AsyncSession) -> None:
    """AP-03's acceptance line: a role change takes effect on the user's next
    login/header-stub resolution — no code change, no restart."""
    ctx = _ctx("demo-mga", Role.ADMIN)
    created = await create_user(
        mem_session, ctx, email="promote@example.com", name="P", role="junior"
    )
    before = await get_ctx(
        mem_session, x_tenant_id="demo-mga", x_user_id=created.id, x_role="junior"
    )
    assert before.role is Role.JUNIOR

    await update_user(mem_session, ctx, created.id, role="senior", name=None)
    after = await get_ctx(
        mem_session, x_tenant_id="demo-mga", x_user_id=created.id, x_role="senior"
    )
    assert after.role is Role.SENIOR


async def test_update_user_scoped_to_caller_tenant(mem_session: AsyncSession) -> None:
    mem_session.add(Tenant(id="other-tenant", name="Other", vertical=Vertical.MGA))
    await mem_session.commit()
    other_ctx = _ctx("other-tenant", Role.ADMIN)
    other_user = await create_user(
        mem_session, other_ctx, email="isolated@example.com", name="I", role="junior"
    )
    admin_ctx = _ctx("demo-mga", Role.ADMIN)
    with pytest.raises(UserNotFoundError):
        await update_user(mem_session, admin_ctx, other_user.id, role="senior", name=None)


async def test_list_users_scoped_to_tenant(mem_session: AsyncSession) -> None:
    mem_session.add(Tenant(id="tenant-b", name="B", vertical=Vertical.MGA))
    await mem_session.commit()
    await create_user(
        mem_session, _ctx("demo-mga", Role.ADMIN), email="a1@example.com", name="A1", role="junior"
    )
    await create_user(
        mem_session, _ctx("tenant-b", Role.ADMIN), email="b1@example.com", name="B1", role="junior"
    )
    a_users = await list_users(mem_session, _ctx("demo-mga", Role.ADMIN))
    assert {u.email for u in a_users} == {"a1@example.com"}


# ── AP-04: settings ───────────────────────────────────────


async def test_list_settings_defaults_to_env_source(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    settings = await list_settings(mem_session, ctx)
    assert {s.key for s in settings} == settings_override_module.SETTING_KEYS
    cap_row = next(s for s in settings if s.key == "junior_premium_cap")
    assert cap_row.source == "env_default"
    assert cap_row.value == str(get_settings().junior_premium_cap)


async def test_save_setting_overrides_and_takes_effect_immediately(
    mem_session: AsyncSession,
) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    out = await save_setting(mem_session, ctx, "carrier_appetite_min_total_outcomes", "5")
    assert out.source == "admin_override"
    assert out.value == "5"
    # no restart, no re-read from DB needed — the in-process cache is already warm
    effective = get_effective_setting(
        "demo-mga", "carrier_appetite_min_total_outcomes",
        get_settings().carrier_appetite_min_total_outcomes,
    )
    assert effective == 5


async def test_clear_setting_reverts_to_env_default(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    await save_setting(mem_session, ctx, "connectors_mode", "live")
    cleared = await clear_setting(mem_session, ctx, "connectors_mode")
    assert cleared.source == "env_default"
    assert cleared.value == "mock"


async def test_save_setting_rejects_unknown_key(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    with pytest.raises(InvalidSettingError):
        await save_setting(mem_session, ctx, "not_a_real_setting", "x")


async def test_save_setting_rejects_invalid_connectors_mode(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    with pytest.raises(InvalidSettingError):
        await save_setting(mem_session, ctx, "connectors_mode", "sandbox")


async def test_save_setting_rejects_non_numeric_value(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    with pytest.raises(InvalidSettingError):
        await save_setting(mem_session, ctx, "quote_rank_price_weight", "not-a-number")


async def test_settings_are_tenant_scoped(mem_session: AsyncSession) -> None:
    mem_session.add(Tenant(id="tenant-c", name="C", vertical=Vertical.MGA))
    await mem_session.commit()
    await save_setting(mem_session, _ctx("demo-mga", Role.ADMIN), "connectors_mode", "live")
    other_settings = await list_settings(mem_session, _ctx("tenant-c", Role.ADMIN))
    other_mode = next(s for s in other_settings if s.key == "connectors_mode")
    assert other_mode.source == "env_default"


# ── AP-06: audit ──────────────────────────────────────────


async def test_query_audit_orders_recent_first_and_respects_limit(
    mem_session: AsyncSession,
) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    audit = DefaultAuditService()
    for i in range(3):
        await audit.record(
            mem_session, ctx,
            AuditEntry(
                actor="human", who=f"u{i}", what=f"action {i}", workflow="binder_issuance",
                tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            ),
        )
    entries = await query_audit(mem_session, ctx, workflow=None, actor=None, limit=2)
    assert len(entries) == 2
    assert entries[0].what == "action 2"  # most recent first


# ── Overview ──────────────────────────────────────────────


async def test_overview_composes_tenant_connections_and_audit(mem_session: AsyncSession) -> None:
    ctx = _ctx("demo-mga", Role.ADMIN)
    out = await get_overview(mem_session, ctx, audit_limit=5)
    assert out.tenant.id == "demo-mga"
    assert out.connections == []  # nothing connected in this throwaway DB
    assert out.recent_audit == []
