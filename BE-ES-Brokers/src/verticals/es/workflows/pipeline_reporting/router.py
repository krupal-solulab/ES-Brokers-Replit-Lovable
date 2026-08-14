"""Routes under ``/api/es/pipeline-reporting`` (docs/WORKFLOW_TEMPLATE.md
step 5). Registered by ``verticals/es/router.py`` — the one shared-file
line the E&S dev touches to mount a workflow.

Per the approved plan: ``run``/``list``/``detail`` only — no
``approve``/``escalate``. A report isn't a determination or a draft
communication a human approves or declines; there is nothing
consequential being gated here, so adding an action endpoint would be
action for its own sake. Every ``/run`` call still enqueues a
``ReviewItem`` (same uniform pattern every prior workflow uses), which is
enough for audit/history visibility.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.common.dtos import Ctx, WorkflowInput
from core.config import get_settings
from core.db import get_session
from core.ingestion import build_connector_service, resolve_sheet_id, try_append_rows
from core.llm import build_llm_service
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.review_queue import DefaultReviewQueueService
from core.tenancy.dependencies import get_ctx
from verticals.es.workflows.pipeline_reporting.schema import PipelineReportPayload
from verticals.es.workflows.pipeline_reporting.service import (
    DEFAULT_WORKFLOW_N,
    WORKFLOW_NAME,
    PipelineReportingPipeline,
)

router = APIRouter(prefix="/pipeline-reporting", tags=["es:pipeline-reporting"])

_SHEET_TAB = "Pipeline Reporting"
_SHEET_HEADER = [
    "Report ID", "Period", "Data Completeness", "Overall Conversion %",
    "Carriers Reported", "Low-Volume Carriers", "Data Gaps", "Exported At",
]

CtxDep = Annotated[Ctx, Depends(get_ctx)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _pipeline() -> PipelineReportingPipeline:
    return PipelineReportingPipeline(llm=build_llm_service(), workflow_n=DEFAULT_WORKFLOW_N)


class RunRequest(BaseModel):
    scenario_ref: str


class ReviewItemOut(BaseModel):
    id: str
    submission_id: str | None
    status: str
    payload: PipelineReportPayload | None = None


async def _pkg_row_for(session: AsyncSession, item: ReviewItemRow) -> OutputPackageRow | None:
    if not item.output_package_id:
        return None
    return (
        await session.execute(
            select(OutputPackageRow).where(col(OutputPackageRow.id) == item.output_package_id)
        )
    ).scalar_one_or_none()


@router.post("/run", status_code=status.HTTP_201_CREATED)
async def run_pipeline_reporting(
    body: RunRequest, ctx: CtxDep, session: SessionDep
) -> ReviewItemOut:
    pipeline = _pipeline()
    output = await pipeline.run(ctx, WorkflowInput(source_ref=body.scenario_ref))

    review_queue = DefaultReviewQueueService()
    item = await review_queue.enqueue(session, ctx, output, WORKFLOW_NAME)
    return ReviewItemOut(
        id=item.id, submission_id=item.submission_id, status=item.status.value,
        payload=PipelineReportPayload(**output.payload),
    )


@router.post("/run-live", status_code=status.HTTP_201_CREATED)
async def run_pipeline_reporting_live(ctx: CtxDep, session: SessionDep) -> ReviewItemOut:
    """Additive alongside ``/run`` above: builds one report from real
    cross-workflow ``OutputPackage`` rows for this tenant (Market Matching,
    Package Assembly, Quote Comparison, Binder Issuance, Renewal
    Remarketing) instead of the Workflow_19 fixture. See
    ``live_aggregator.py``."""
    pipeline = _pipeline()
    output = await pipeline.run_live(ctx, session)

    review_queue = DefaultReviewQueueService()
    item = await review_queue.enqueue(session, ctx, output, WORKFLOW_NAME)
    return ReviewItemOut(
        id=item.id, submission_id=item.submission_id, status=item.status.value,
        payload=PipelineReportPayload(**output.payload),
    )


@router.get("")
async def list_pipeline_reporting(ctx: CtxDep, session: SessionDep) -> list[ReviewItemOut]:
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
async def get_pipeline_reporting(item_id: str, ctx: CtxDep, session: SessionDep) -> ReviewItemOut:
    item = (
        await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.id) == item_id, col(ReviewItemRow.tenant_id) == ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no pipeline-reporting review item '{item_id}'"
        )
    pkg = await _pkg_row_for(session, item)
    return ReviewItemOut(
        id=item.id, submission_id=item.submission_id, status=item.status.value,
        payload=PipelineReportPayload(**pkg.payload) if pkg and pkg.payload else None,
    )


class ExportToSheetOut(BaseModel):
    status: str  # ok | skipped-no-sheet-id | skipped-not-connected | failed


@router.post("/{item_id}/export-to-sheet")
async def export_to_sheet(item_id: str, ctx: CtxDep, session: SessionDep) -> ExportToSheetOut:
    """Broker-triggered manual export — pushes one summary row for this report
    into the tenant's connected Google Sheet (core/ingestion/writeback.py),
    on the same Sheets write-back precedent as the MGA workflows' auto-
    write-back on approve. Manual here, not automatic, because this router
    has no approve/decision gate to hook a write-back into (a report isn't
    a determination a human approves, per this module's own docstring) —
    the broker explicitly asks for the export instead. Never fails hard on
    a missing sheet id or unconnected Sheets integration; that's a normal
    logged skip, same as every other write-back call site."""
    item = (
        await session.execute(
            select(ReviewItemRow).where(
                col(ReviewItemRow.id) == item_id, col(ReviewItemRow.tenant_id) == ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no pipeline-reporting review item '{item_id}'"
        )
    pkg = await _pkg_row_for(session, item)
    if pkg is None or not pkg.payload:
        raise HTTPException(status.HTTP_409_CONFLICT, "report has no payload to export")
    payload = PipelineReportPayload(**pkg.payload)

    sheet_id = await resolve_sheet_id(session, ctx.tenant_id, get_settings())
    connector = build_connector_service(session=session, tenant_id=ctx.tenant_id)
    row = [
        payload.report_id,
        payload.period,
        payload.data_completeness.status,
        payload.overall_conversion_pct,
        len(payload.carrier_performance),
        sum(1 for c in payload.carrier_performance if c.low_volume_flag),
        len(payload.data_completeness.gaps),
        datetime.now(UTC).isoformat(),
    ]
    result = await try_append_rows(
        connector, ctx, sheet_id, [row], tab=_SHEET_TAB, header=_SHEET_HEADER
    )
    return ExportToSheetOut(status=result)
