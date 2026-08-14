"""Dev seed script — inserts demo tenants + users so the header-stub auth and the
vertical lookup work immediately in dev.

Creates (idempotently, checked per-user so re-running after adding new users
to `_USERS` below still seeds the new ones even though the tenant already
exists):
  - Tenant "demo-es"   (vertical ES)  with a junior + a senior + an admin
    user, plus three real-email login users for the email-based-role login
    feature (``manager.j@gmail.com`` -> junior, ``manager.s@gmail.com`` ->
    senior, ``manager.a@gmail.com`` -> admin — the Admin Panel's prerequisite
    seed user, PRD_Admin_Panel.md §9)

Every admin-role user also gets a password set (see ``_DEV_ADMIN_PASSWORD``)
so they can use the Admin Panel's password-checked ``POST
/api/core/auth/admin-login`` — junior/senior users never get a password
and can only ever use the original email-only ``POST /api/core/auth/login``.
Re-running this script also backfills the password onto an admin user row
that already exists from before this feature, not just newly-created ones.

Run (from the repo root, with the venv active):
    python -m core.seed          # if src is on PYTHONPATH
    python src/core/seed.py      # self-bootstraps src onto sys.path
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow direct execution (`python src/core/seed.py`) by putting src/ on the path.
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sqlmodel import col, select  # noqa: E402

from core.auth.password import hash_password  # noqa: E402
from core.common.enums import Role, Vertical  # noqa: E402
from core.db import async_session_factory  # noqa: E402
from core.models import Tenant, User  # noqa: E402

# Dev-only credential for every seeded admin account — not a secret, this is
# a local SQLite dev database. An admin-managed "change password" action
# doesn't exist yet; this is the only way any admin password gets set today.
_DEV_ADMIN_PASSWORD = "Pa$$w0rd!"

_TENANTS = [
    ("demo-es", "Demo E&S Brokerage", Vertical.ES),
]

_USERS = [
    # (tenant_id, user_id, email, display_name, role, password)
    ("demo-es", "demo-es-junior", "junior@demo-es.example", "Demo Junior", Role.JUNIOR, None),
    ("demo-es", "demo-es-senior", "senior@demo-es.example", "Demo Senior", Role.SENIOR, None),
    (
        "demo-es", "demo-es-admin", "admin@demo-es.example", "Demo Admin", Role.ADMIN,
        _DEV_ADMIN_PASSWORD,
    ),
    # Real-email login users (email-based-role login feature) — the email
    # itself is what determines the role, per the login endpoint's lookup.
    ("demo-es", "demo-es-manager-j", "manager.j@gmail.com", "Manager J", Role.JUNIOR, None),
    ("demo-es", "demo-es-manager-s", "manager.s@gmail.com", "Manager S", Role.SENIOR, None),
    # Admin Panel prerequisite (PRD_Admin_Panel.md §9) — no admin user was seeded
    # anywhere before this, which blocked every AP-0x acceptance test.
    (
        "demo-es", "demo-es-manager-a", "manager.a@gmail.com", "Manager A", Role.ADMIN,
        _DEV_ADMIN_PASSWORD,
    ),
]


async def seed() -> None:
    async with async_session_factory() as session:
        for tenant_id, name, vertical in _TENANTS:
            existing = (
                await session.execute(select(Tenant).where(col(Tenant.id) == tenant_id))
            ).scalar_one_or_none()
            if existing is None:
                session.add(Tenant(id=tenant_id, name=name, vertical=vertical))
                print(f"+ seeded tenant '{tenant_id}' ({vertical})")
            else:
                print(f"= tenant '{tenant_id}' already exists, skipping")
        await session.commit()

        for tenant_id, user_id, email, display_name, role, password in _USERS:
            existing_user = (
                await session.execute(select(User).where(col(User.id) == user_id))
            ).scalar_one_or_none()
            if existing_user is None:
                session.add(
                    User(
                        id=user_id, tenant_id=tenant_id, email=email, name=display_name, role=role,
                        password_hash=hash_password(password) if password else None,
                    )
                )
                print(f"+ seeded user '{email}' ({role.value}) for tenant '{tenant_id}'")
            elif password and not existing_user.password_hash:
                existing_user.password_hash = hash_password(password)
                session.add(existing_user)
                print(f"~ set password on existing admin user '{email}'")
            else:
                print(f"= user '{email}' already exists, skipping")
        await session.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
