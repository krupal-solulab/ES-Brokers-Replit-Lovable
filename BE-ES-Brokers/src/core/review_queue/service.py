"""Review queue persistence + RBAC/authority-gated actions."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.admin.settings_override import get_effective_setting
from core.auth import can_approve
from core.common.dtos import Ctx
from core.common.dtos import OutputPackage as OutputPackageDTO
from core.common.dtos import ReviewItem as ReviewItemDTO
from core.common.enums import ReviewAction, ReviewStatus, Role
from core.config import get_settings
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.models import Tenant
from core.submissions import ensure_submission

# Actions restricted to senior/admin regardless of amount.
_SENIOR_ACTIONS = {ReviewAction.OVERRIDE, ReviewAction.SEND, ReviewAction.ISSUE}

_ACTION_STATUS = {
    ReviewAction.APPROVE: ReviewStatus.APPROVED,
    ReviewAction.OVERRIDE: ReviewStatus.OVERRIDDEN,
    ReviewAction.ESCALATE: ReviewStatus.ESCALATED,
    ReviewAction.SEND: ReviewStatus.SENT,
    ReviewAction.ISSUE: ReviewStatus.ISSUED,
}


class AuthorityError(Exception):
    """Raised when a user's role/authority does not permit the requested action."""


class ReviewQueueService(Protocol):
    async def enqueue(
        self, session: AsyncSession, ctx: Ctx, output: OutputPackageDTO, workflow: str
    ) -> ReviewItemDTO: ...
    async def act(
        self,
        session: AsyncSession,
        ctx: Ctx,
        item_id: str,
        action: ReviewAction,
        amount: float | None = None,
    ) -> ReviewItemDTO: ...


class DefaultReviewQueueService:
    async def enqueue(
        self, session: AsyncSession, ctx: Ctx, output: OutputPackageDTO, workflow: str
    ) -> ReviewItemDTO:
        # OutputPackage/ReviewItem both foreign-key onto submission.id, but
        # several workflows pass a submission_id that was never backed by a
        # real Submission row (a live bind's own id, a review item's own id,
        # etc.) — see core/submissions.py. Every workflow enqueues through
        # here, so fixing it once here covers all of them.
        if output.submission_id:
            await ensure_submission(session, ctx, output.submission_id)
        pkg = OutputPackageRow(
            tenant_id=ctx.tenant_id,
            submission_id=output.submission_id or "",
            workflow=workflow,
            payload=output.payload or None,
        )
        session.add(pkg)
        await session.flush()

        item = ReviewItemRow(
            tenant_id=ctx.tenant_id,
            submission_id=output.submission_id,
            output_package_id=pkg.id,
            workflow=workflow,
            status=ReviewStatus.PENDING,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return ReviewItemDTO(
            id=item.id, submission_id=item.submission_id, workflow=workflow,
            status=item.status, output=output,
        )

    async def act(
        self,
        session: AsyncSession,
        ctx: Ctx,
        item_id: str,
        action: ReviewAction,
        amount: float | None = None,
    ) -> ReviewItemDTO:
        item = (
            await session.execute(
                select(ReviewItemRow).where(
                    col(ReviewItemRow.id) == item_id,
                    col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise KeyError(f"review item '{item_id}' not found for tenant")

        cap = (
            await self._resolve_junior_cap(session, ctx.tenant_id)
            if action is ReviewAction.APPROVE
            else None
        )
        self._authorize(ctx.role, action, amount, cap=cap)
        item.status = _ACTION_STATUS[action]
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return ReviewItemDTO(
            id=item.id, submission_id=item.submission_id, workflow=item.workflow,
            status=item.status, output=None,
        )

    @staticmethod
    async def _resolve_junior_cap(session: AsyncSession, tenant_id: str) -> float:
        """Precedence: Tenant.junior_premium_cap (AP-02's per-tenant override) >
        an admin's PlatformSetting override (AP-04) > the env default."""
        tenant = (
            await session.execute(select(Tenant).where(col(Tenant.id) == tenant_id))
        ).scalar_one_or_none()
        if tenant is not None and tenant.junior_premium_cap is not None:
            return tenant.junior_premium_cap
        return get_effective_setting(
            tenant_id, "junior_premium_cap", get_settings().junior_premium_cap
        )

    @staticmethod
    def _authorize(
        role: Role, action: ReviewAction, amount: float | None, *, cap: float | None = None
    ) -> None:
        if action is ReviewAction.ESCALATE:
            return  # anyone may escalate
        if action in _SENIOR_ACTIONS and role is Role.JUNIOR:
            raise AuthorityError(f"role '{role}' may not '{action.value}' (senior/admin only)")
        if action is ReviewAction.APPROVE and not can_approve(role, amount, cap=cap):
            raise AuthorityError(
                f"junior approval over authority cap (amount={amount}); must escalate"
            )
