"""Shared guard for a recurring FK gap: ``Document``, ``OutputPackage``, and
``ReviewItem`` all foreign-key onto ``submission.id``, but several real call
sites pass a ``submission_id`` that was never actually backed by a
``Submission`` row — a fixture/live scenario ref (e.g. Market Matching's
``"submission_01"``), or another entity's own id reused as a stable
grouping key (e.g. Binder Issuance's ``bind_id``, a review item's own id).
Invisible on SQLite (FK enforcement is off by default there); a hard failure
on Postgres.

Call this once, before the first insert that references the id, from
``core/review_queue/service.py``'s ``enqueue()`` (covers ``OutputPackage`` +
``ReviewItem`` in one place) and ``core/documents/store.py``'s ``save()``
(covers ``Document``) — rather than re-implementing the same check at every
workflow's own call site.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.common.dtos import Ctx
from core.models import Submission


async def ensure_submission(session: AsyncSession, ctx: Ctx, submission_id: str) -> None:
    existing = (
        await session.execute(select(Submission).where(col(Submission.id) == submission_id))
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            Submission(
                id=submission_id, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
                external_ref=submission_id, subject=submission_id, status="received",
            )
        )
        await session.flush()
