"""Routes under ``/api/es/market-matching`` (docs/WORKFLOW_TEMPLATE.md step 5).
Registered by ``verticals/es/router.py`` — the one shared-file line the E&S dev
touches to mount a workflow.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.audit import DefaultAuditService
from core.common.dtos import AuditEntry as AuditEntryDTO
from core.common.dtos import Ctx, WorkflowInput
from core.common.enums import ReviewAction, Role
from core.db import get_session
from core.documents import LocalDocumentStore
from core.extraction import DefaultExtractionService
from core.ingestion.connectors import ConnectorNotConnectedError, build_connector_service
from core.llm import build_llm_service
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.review_queue import AuthorityError, DefaultReviewQueueService
from core.rules_engine import DefaultRulesEngine
from core.tenancy.dependencies import get_ctx
from verticals.es.agent_communication_hooks import fire_no_market_found
from verticals.es.diligent_search_hooks import fire_diligent_search_required
from verticals.es.workflows.market_matching.schema import (
    CarrierMatchOut,
    MarketMatchingPayload,
)
from verticals.es.workflows.market_matching.service import (
    DEFAULT_WORKFLOW_N,
    WORKFLOW_NAME,
    MarketMatchingPipeline,
)

# Relative prefix only — verticals/es/router.py (already "/api/es") includes this,
# producing the full "/api/es/market-matching" path. Do not add "/api/es" here.
router = APIRouter(prefix="/market-matching", tags=["es:market-matching"])

CtxDep = Annotated[Ctx, Depends(get_ctx)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _pipeline(session: AsyncSession, tenant_id: str | None = None) -> MarketMatchingPipeline:
    return MarketMatchingPipeline(
        session=session,
        connector=build_connector_service(
            workflow_n=DEFAULT_WORKFLOW_N, session=session, tenant_id=tenant_id
        ),
        extraction=DefaultExtractionService(),
        rules_engine=DefaultRulesEngine(),
        llm=build_llm_service(tenant_id=tenant_id),
        documents=LocalDocumentStore(),
        workflow_n=DEFAULT_WORKFLOW_N,
    )


class RunRequest(BaseModel):
    submission_ref: str  # e.g. "submission_01" — the fixture/Nango message id


class ReviewItemOut(BaseModel):
    id: str
    submission_id: str | None
    status: str
    payload: MarketMatchingPayload | None = None


class DocumentOut(BaseModel):
    filename: str
    kind: str
    content: str


class LiveInboxMessageOut(BaseModel):
    id: str
    subject: str


@router.get("/live-inbox")
async def list_live_inbox(ctx: CtxDep, session: SessionDep) -> list[LiveInboxMessageOut]:
    """Real Gmail messages (via the connected Nango integration) to pick from and
    run through `/run` as a real ``submission_ref`` — additive alongside the
    fixture-scenario path; requires Gmail connected + CONNECTORS_MODE=live."""
    connector = build_connector_service(
        workflow_n=DEFAULT_WORKFLOW_N, session=session, tenant_id=ctx.tenant_id
    )
    try:
        messages = await connector.fetch_inbox(ctx)
    except ConnectorNotConnectedError as exc:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            f"Connect Gmail in Settings first ({exc.provider} not connected)",
        ) from exc
    return [LiveInboxMessageOut(id=m.id, subject=m.subject) for m in messages]


@router.post("/run", status_code=status.HTTP_201_CREATED)
async def run_market_matching(body: RunRequest, ctx: CtxDep, session: SessionDep) -> ReviewItemOut:
    """Runs the full pipeline for one submission and enqueues the result for
    human review — nothing here binds/sends anything (human-in-the-loop)."""
    pipeline = _pipeline(session, tenant_id=ctx.tenant_id)
    inp = WorkflowInput(submission_id=body.submission_ref, source_ref=body.submission_ref)
    output = await pipeline.run(ctx, inp)

    review_queue = DefaultReviewQueueService()
    item = await review_queue.enqueue(session, ctx, output, WORKFLOW_NAME)
    await fire_no_market_found(session, ctx, output)  # additive, no-throw — see module docstring
    await fire_diligent_search_required(session, ctx, output)  # additive, no-throw — MM-07
    return ReviewItemOut(
        id=item.id, submission_id=item.submission_id, status=item.status.value,
        payload=output.payload,
    )


@router.get("")
async def list_market_matching(ctx: CtxDep, session: SessionDep) -> list[ReviewItemOut]:
    rows = (
        await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.tenant_id) == ctx.tenant_id,
                col(ReviewItemRow.workflow) == WORKFLOW_NAME,
            )
        )
    ).scalars().all()
    return [
        ReviewItemOut(id=r.id, submission_id=r.submission_id, status=r.status.value) for r in rows
    ]


@router.get("/{item_id}")
async def get_market_matching(item_id: str, ctx: CtxDep, session: SessionDep) -> ReviewItemOut:
    item = (
        await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.id) == item_id, col(ReviewItemRow.tenant_id) == ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no market-matching review item '{item_id}'"
        )
    payload = None
    if item.output_package_id:
        pkg = (
            await session.execute(
                select(OutputPackageRow).where(col(OutputPackageRow.id) == item.output_package_id)
            )
        ).scalar_one_or_none()
        payload = pkg.payload if pkg else None
    return ReviewItemOut(
        id=item.id, submission_id=item.submission_id, status=item.status.value, payload=payload
    )


@router.get("/{item_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    item_id: str, ctx: CtxDep, session: SessionDep
) -> list[DocumentOut]:
    """The raw documents `ingest()` persisted via `LocalDocumentStore` for this
    submission — real fixture content, not extracted/cited fields (see
    core/extraction for that)."""
    item = (
        await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.id) == item_id, col(ReviewItemRow.tenant_id) == ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if item is None or item.submission_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no market-matching review item '{item_id}'"
        )
    docs = await LocalDocumentStore().list_for_submission(session, ctx, item.submission_id)
    return [DocumentOut(filename=d.filename, kind=d.kind.value, content=d.content) for d in docs]


async def _act(
    item_id: str, action: ReviewAction, ctx: Ctx, session: AsyncSession
) -> ReviewItemOut:
    review_queue = DefaultReviewQueueService()
    try:
        item = await review_queue.act(session, ctx, item_id, action)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except AuthorityError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return ReviewItemOut(id=item.id, submission_id=item.submission_id, status=item.status.value)


@router.post("/{item_id}/approve")
async def approve(item_id: str, ctx: CtxDep, session: SessionDep) -> ReviewItemOut:
    return await _act(item_id, ReviewAction.APPROVE, ctx, session)


class OverrideExclusionRequest(BaseModel):
    """A senior/admin includes a HARD-EXCLUDED carrier in the shortlist anyway.
    A typed reason is mandatory — an override never silently flips anything."""

    carrier_id: str
    reason: str


@router.post("/{item_id}/override")
async def override_exclusion(
    item_id: str, body: OverrideExclusionRequest, ctx: CtxDep, session: SessionDep
) -> ReviewItemOut:
    """Moves one hard-excluded carrier into the selectable shortlist (audited).

    The overridden carrier carries NO engine score (KB06 — the deterministic
    score is engine output only; a manual override does not invent one) and
    keeps the rule it broke, so downstream screens can show it was forced in.
    """
    if ctx.role not in (Role.SENIOR, Role.ADMIN):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "override requires a senior or admin role"
        )
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "a typed override reason is required"
        )

    item = (
        await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.id) == item_id, col(ReviewItemRow.tenant_id) == ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if item is None or not item.output_package_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no market-matching review item '{item_id}'"
        )
    pkg = (
        await session.execute(
            select(OutputPackageRow).where(col(OutputPackageRow.id) == item.output_package_id)
        )
    ).scalar_one_or_none()
    if pkg is None or not pkg.payload:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "review item has no payload")

    payload = MarketMatchingPayload(**pkg.payload)
    excluded_row = next((e for e in payload.excluded if e.carrier_id == body.carrier_id), None)
    if excluded_row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"carrier '{body.carrier_id}' is not in this item's excluded list",
        )

    payload.excluded = [e for e in payload.excluded if e.carrier_id != body.carrier_id]
    payload.matches.append(
        CarrierMatchOut(
            carrier_id=excluded_row.carrier_id,
            carrier_name=excluded_row.carrier_name,
            score=0.0,  # no engine score — manual inclusion, never AI/heuristic
            missing=[],
            flags=[f"Manually overridden: was hard-excluded by {excluded_row.rule}"],
            overridden=True,
            override_rule=excluded_row.rule,
            override_reason=reason,
        )
    )
    pkg.payload = payload.model_dump()
    session.add(pkg)

    await DefaultAuditService().record(
        session, ctx,
        AuditEntryDTO(
            actor="human", who=ctx.user_id,
            what=f"exclusion override: {excluded_row.carrier_name} ({excluded_row.rule})",
            workflow=WORKFLOW_NAME, tenant_id=ctx.tenant_id, vertical=ctx.vertical,
            detail={
                "review_item_id": item_id,
                "submission_id": item.submission_id,
                "carrier_id": excluded_row.carrier_id,
                "carrier_name": excluded_row.carrier_name,
                "rule_overridden": excluded_row.rule,
                "reason": reason,
            },
        ),
    )
    await session.commit()
    await session.refresh(pkg)
    return ReviewItemOut(
        id=item.id, submission_id=item.submission_id, status=item.status.value,
        payload=pkg.payload,
    )


@router.post("/{item_id}/escalate")
async def escalate(item_id: str, ctx: CtxDep, session: SessionDep) -> ReviewItemOut:
    return await _act(item_id, ReviewAction.ESCALATE, ctx, session)


# NOTE: no /send endpoint — "sending" from Market Matching is the audited
# handoff to Package Assembly (POST /package-assembly/run-from-market-matching
# with carrier_ids), never a bare status flip and never a carrier email.
# NOTE: no /issue endpoint — "issue" is a binder concept, not a Market Matching
# action. Proceeding from here is the Send handoff to Package Assembly (FR-13).
