"""Routes under ``/api/es/carrier-profiles`` — G2 Carrier Appetite Profile Store.

Endpoints
---------
GET  /                                     list current profile versions (any auth role)
GET  /{carrier_id}                         current + version history
POST /{carrier_id}                         create a new version (human edit) — SENIOR/ADMIN
POST /{carrier_id}/suggestions/{sid}/approve  apply a pending CI suggestion — SENIOR/ADMIN
POST /{carrier_id}/suggestions/{sid}/dismiss  mark a CI suggestion dismissed — SENIOR/ADMIN
POST /seed                                 seed DB from JSON panel (ADMIN only, idempotent)

Lazy seed: the list endpoint auto-seeds from the JSON panel for this tenant on first call
if the store is empty, so "no behaviour change on day one" holds even before the operator
calls ``/seed`` manually.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from fastapi.params import Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.auth import require_roles
from core.common.dtos import Ctx
from core.common.enums import Role
from core.db import get_session
from core.models import CarrierAppetiteProfile as ProfileRow
from core.models import OutputPackage as OutputPackageRow
from core.models import ReviewItem as ReviewItemRow
from core.tenancy.dependencies import get_ctx
from verticals.es.carrier_profile_store import (
    CarrierProfileService,
    MetadataRefreshDTO,
    SOURCE_HUMAN_EDIT,
    profile_row_to_carrier,
)
from verticals.es.decision_core.carrier_profiles import load_carrier_panel

router = APIRouter(prefix="/carrier-profiles", tags=["es:carrier-profiles"])

CtxDep = Annotated[Ctx, Depends(get_ctx)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SeniorCtxDep = Annotated[Ctx, Depends(require_roles(Role.SENIOR, Role.ADMIN))]
AdminCtxDep = Annotated[Ctx, Depends(require_roles(Role.ADMIN))]

# Workflow_10 hosts the real carrier panel JSON fixtures.
_CARRIER_PANEL_WORKFLOW_N = 10

# CAR-06 gap_policy seeded from the old hardcoded _CARRIER_POLICY_OVERRIDES in assembly.py.
_SEED_GAP_POLICY_OVERRIDES: dict[str, dict[str, str]] = {
    "CAR-06": {"missing_document_type": "disclose"},
}


# ── Output DTOs ───────────────────────────────────────────────────────────────

class CarrierProfileVersionOut(BaseModel):
    version_id: str
    carrier_id: str
    carrier_name: str
    class_codes_accepted: list[str]
    class_codes_excluded: list[str]
    states_licensed: list[str]
    premium_band: dict[str, Any]
    submission_requirements: dict[str, Any]
    severity_ceiling: dict[str, Any]
    appetite_confidence: str
    appetite_last_updated: str | None
    historical_hit_rate_this_class: float
    lines_written: list[str]
    notes: str | None
    form_metadata: dict[str, Any]
    gap_policy: dict[str, str]
    supersedes_version_id: str | None
    created_at: str
    created_by: str
    source: str


class CarrierProfileWithHistoryOut(BaseModel):
    current: CarrierProfileVersionOut | None
    history: list[CarrierProfileVersionOut]


class SuggestionActionOut(BaseModel):
    suggestion_id: str
    carrier_id: str
    action: str  # APPROVED | DISMISSED
    profile_version_id: str | None = None  # populated on approve


# ── Write DTO ─────────────────────────────────────────────────────────────────

class CarrierProfileUpdateIn(BaseModel):
    carrier_name: str
    class_codes_accepted: list[str] = []
    class_codes_excluded: list[str] = []
    states_licensed: list[str] = []
    premium_band: dict[str, Any] = {}
    submission_requirements: dict[str, Any] = {}
    severity_ceiling: dict[str, Any] = {}
    appetite_confidence: str = "medium"
    appetite_last_updated: str | None = None
    historical_hit_rate_this_class: float = 0.5
    lines_written: list[str] = []
    notes: str | None = None
    form_metadata: dict[str, Any] = {}
    gap_policy: dict[str, str] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_out(row: ProfileRow) -> CarrierProfileVersionOut:
    return CarrierProfileVersionOut(
        version_id=row.version_id,
        carrier_id=row.carrier_id,
        carrier_name=row.carrier_name,
        class_codes_accepted=list(row.class_codes_accepted or []),
        class_codes_excluded=list(row.class_codes_excluded or []),
        states_licensed=list(row.states_licensed or []),
        premium_band=dict(row.premium_band or {}),
        submission_requirements=dict(row.submission_requirements or {}),
        severity_ceiling=dict(row.severity_ceiling or {}),
        appetite_confidence=row.appetite_confidence,
        appetite_last_updated=row.appetite_last_updated,
        historical_hit_rate_this_class=row.historical_hit_rate_this_class,
        lines_written=list(row.lines_written or []),
        notes=row.notes,
        form_metadata=dict(row.form_metadata or {}),
        gap_policy=dict(row.gap_policy or {}),
        supersedes_version_id=row.supersedes_version_id,
        created_at=row.created_at.isoformat(),
        created_by=row.created_by,
        source=row.source,
    )


async def _auto_seed(session: AsyncSession, tenant_id: str) -> None:
    """Auto-seed the profile store from the JSON panel if empty for this tenant.

    Idempotent: ``seed_from_json`` skips carriers that already have a row.
    """
    panel = load_carrier_panel(_CARRIER_PANEL_WORKFLOW_N)
    if panel:
        await CarrierProfileService.seed_from_json(
            session,
            tenant_id,
            panel,
            gap_policy_overrides=_SEED_GAP_POLICY_OVERRIDES,
        )


async def _find_suggestion(
    session: AsyncSession,
    tenant_id: str,
    carrier_id: str,
    suggestion_id: str,
) -> tuple[ReviewItemRow, OutputPackageRow, dict[str, Any]]:
    """Locate a CI suggestion by ``suggestion_id`` across all review items for this tenant.

    Returns (review_item, output_package, payload_dict) or raises 404.
    """
    items_result = await session.execute(
        select(ReviewItemRow).where(
            col(ReviewItemRow.tenant_id) == tenant_id,
        )
    )
    items = list(items_result.scalars().all())

    for item in items:
        if not item.output_package_id:
            continue
        pkg = (
            await session.execute(
                select(OutputPackageRow).where(
                    col(OutputPackageRow.id) == item.output_package_id
                )
            )
        ).scalar_one_or_none()
        if pkg is None or not pkg.payload:
            continue
        payload = pkg.payload
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                continue
        sid_found = payload.get("suggestion_id")
        cid_found = payload.get("carrier_id")
        if sid_found == suggestion_id and cid_found == carrier_id:
            return item, pkg, payload

    raise HTTPException(
        status.HTTP_404_NOT_FOUND,
        f"no pending suggestion '{suggestion_id}' for carrier '{carrier_id}'",
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[CarrierProfileVersionOut])
async def list_carrier_profiles(ctx: CtxDep, session: SessionDep) -> list[CarrierProfileVersionOut]:
    """List the current (latest) version of every carrier profile for this tenant.

    Auto-seeds from the JSON panel on first call if the store is empty.
    """
    rows = await CarrierProfileService.list_current(session, ctx.tenant_id)
    if not rows:
        await _auto_seed(session, ctx.tenant_id)
        rows = await CarrierProfileService.list_current(session, ctx.tenant_id)
    return [_row_out(r) for r in rows]


@router.get("/{carrier_id}", response_model=CarrierProfileWithHistoryOut)
async def get_carrier_profile(
    carrier_id: str, ctx: CtxDep, session: SessionDep
) -> CarrierProfileWithHistoryOut:
    current, history = await CarrierProfileService.get_with_history(
        session, ctx.tenant_id, carrier_id
    )
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"carrier profile not found: {carrier_id!r}")
    return CarrierProfileWithHistoryOut(
        current=_row_out(current),
        history=[_row_out(r) for r in history],
    )


@router.post("/{carrier_id}", response_model=CarrierProfileVersionOut, status_code=status.HTTP_201_CREATED)
async def update_carrier_profile(
    carrier_id: str,
    body: CarrierProfileUpdateIn,
    ctx: SeniorCtxDep,
    session: SessionDep,
) -> CarrierProfileVersionOut:
    """Create a new version from a human edit. Previous version is preserved (append-only)."""
    row = await CarrierProfileService.create_version(
        session,
        ctx,
        carrier_id,
        body.model_dump(),
        source=SOURCE_HUMAN_EDIT,
    )
    return _row_out(row)


@router.post(
    "/{carrier_id}/suggestions/{sid}/approve",
    response_model=SuggestionActionOut,
)
async def approve_suggestion(
    carrier_id: str, sid: str, ctx: SeniorCtxDep, session: SessionDep
) -> SuggestionActionOut:
    """Apply a pending CI suggestion as a new CarrierAppetiteProfile version.

    If the suggestion's ``metadata_refresh`` is populated (CI-03 CONFIRMED_CONSISTENT path),
    this calls ``refresh_metadata()`` — the narrow write path. Otherwise the suggestion is
    approved without writing a profile version (e.g. SUPPRESSED suggestions).
    The suggestion's ``status`` field is updated to ``APPROVED`` in the stored payload.
    """
    _item, pkg, payload = await _find_suggestion(session, ctx.tenant_id, carrier_id, sid)

    profile_version_id: str | None = None
    metadata_refresh = payload.get("metadata_refresh")
    if metadata_refresh:
        dto = MetadataRefreshDTO(
            appetite_confidence=metadata_refresh["appetite_confidence"],
            appetite_last_updated=metadata_refresh["appetite_last_updated"],
        )
        row = await CarrierProfileService.refresh_metadata(session, ctx, carrier_id, dto)
        profile_version_id = row.version_id

    # Mark the suggestion as APPROVED in the stored payload.
    updated_payload = {**payload, "status": "APPROVED"}
    pkg.payload = updated_payload  # type: ignore[assignment]
    session.add(pkg)
    await session.commit()

    return SuggestionActionOut(
        suggestion_id=sid,
        carrier_id=carrier_id,
        action="APPROVED",
        profile_version_id=profile_version_id,
    )


@router.post(
    "/{carrier_id}/suggestions/{sid}/dismiss",
    response_model=SuggestionActionOut,
)
async def dismiss_suggestion(
    carrier_id: str, sid: str, ctx: SeniorCtxDep, session: SessionDep
) -> SuggestionActionOut:
    """Mark a CI suggestion as dismissed. No profile version is created."""
    _item, pkg, payload = await _find_suggestion(session, ctx.tenant_id, carrier_id, sid)
    updated_payload = {**payload, "status": "DISMISSED"}
    pkg.payload = updated_payload  # type: ignore[assignment]
    session.add(pkg)
    await session.commit()
    return SuggestionActionOut(
        suggestion_id=sid,
        carrier_id=carrier_id,
        action="DISMISSED",
    )


@router.post("/seed", response_model=dict)
async def seed_carrier_profiles(ctx: AdminCtxDep, session: SessionDep) -> dict:
    """Seed the profile store from the JSON panel (idempotent, ADMIN only).

    Already-seeded carriers are skipped. Returns counts.
    """
    panel = load_carrier_panel(_CARRIER_PANEL_WORKFLOW_N)
    seeded = await CarrierProfileService.seed_from_json(
        session,
        ctx.tenant_id,
        panel,
        gap_policy_overrides=_SEED_GAP_POLICY_OVERRIDES,
    )
    return {"seeded": len(seeded), "total_panel": len(panel)}
