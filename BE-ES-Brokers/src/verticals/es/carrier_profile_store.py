"""Versioned Carrier Appetite Profile store — G2.

Service layer between the HTTP router / pipelines and the ``carrier_appetite_profile``
table.  All writes create a NEW version row; nothing is ever updated or deleted
(KB05 append-only).

Public surface:
  - ``MetadataRefreshDTO``        narrow CI-03 write DTO
  - ``CarrierProfileService``     read + write operations
  - ``profile_row_to_carrier``    DB row → frozen ``CarrierProfile`` dataclass
  - ``PROFILE_SOURCES``           source enum strings
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, desc, select

from core.common.dtos import Ctx
from core.models import CarrierAppetiteProfile as ProfileRow
from verticals.es.decision_core.carrier_profiles import (
    CarrierProfile,
    PremiumBand,
    SeverityCeiling,
    SubmissionRequirements,
    load_carrier_panel,
)

# ── Source constants ──────────────────────────────────────────────────────────

PROFILE_SOURCES = ("SEED", "HUMAN_EDIT", "CI_METADATA_REFRESH")
SOURCE_SEED = "SEED"
SOURCE_HUMAN_EDIT = "HUMAN_EDIT"
SOURCE_CI = "CI_METADATA_REFRESH"


# ── Narrow CI-03 write DTO ────────────────────────────────────────────────────

class MetadataRefreshDTO(BaseModel):
    """Structural gate for CI-03 (FR-4): only confidence + last_updated may be
    supplied. The typed DTO makes it structurally impossible to touch
    class_codes_accepted / _excluded / premium_band / severity_ceiling."""

    appetite_confidence: str  # high | medium | low
    appetite_last_updated: str  # ISO date string


# ── Conversion helper ─────────────────────────────────────────────────────────

def profile_row_to_carrier(row: ProfileRow) -> CarrierProfile:
    """Convert a DB row to the frozen ``CarrierProfile`` dataclass the matching
    engine expects.  ``gap_policy`` and ``form_metadata`` are not part of the
    dataclass — callers that need them should read the row directly."""
    pb = row.premium_band or {}
    sr = row.submission_requirements or {}
    sc = row.severity_ceiling or {}
    return CarrierProfile(
        carrier_id=row.carrier_id,
        carrier_name=row.carrier_name,
        class_codes_accepted=tuple(row.class_codes_accepted or []),
        class_codes_excluded=tuple(row.class_codes_excluded or []),
        states_licensed=tuple(row.states_licensed or []),
        premium_band=PremiumBand(
            min=float(pb.get("min", 0)),
            max=float(pb.get("max", 0)),
        ),
        submission_requirements=SubmissionRequirements(
            min_loss_run_years=int(sr.get("min_loss_run_years", 0)),
            required_documents=tuple(sr.get("required_documents", [])),
            acceptance_window_days=sr.get("acceptance_window_days"),
        ),
        severity_ceiling=SeverityCeiling(
            max_single_claim_incurred=float(sc.get("max_single_claim_incurred", 0))
        ),
        appetite_confidence=row.appetite_confidence,
        historical_hit_rate_this_class=row.historical_hit_rate_this_class,
        lines_written=tuple(row.lines_written or []),
        notes=row.notes or "",
        ceiling_type=None,  # not stored in JSON source; not a substantive field
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _latest_for(
    session: AsyncSession, tenant_id: str, carrier_id: str
) -> ProfileRow | None:
    return (
        await session.execute(
            select(ProfileRow)
            .where(
                col(ProfileRow.tenant_id) == tenant_id,
                col(ProfileRow.carrier_id) == carrier_id,
            )
            .order_by(desc(col(ProfileRow.created_at)))
            .limit(1)
        )
    ).scalar_one_or_none()


async def _all_latest(session: AsyncSession, tenant_id: str) -> list[ProfileRow]:
    """Latest version per carrier_id for a tenant (subquery-free approach:
    fetch all then dedupe in Python — profile counts are small)."""
    rows = list(
        (
            await session.execute(
                select(ProfileRow)
                .where(col(ProfileRow.tenant_id) == tenant_id)
                .order_by(col(ProfileRow.carrier_id), desc(col(ProfileRow.created_at)))
            )
        )
        .scalars()
        .all()
    )
    seen: set[str] = set()
    result: list[ProfileRow] = []
    for r in rows:
        if r.carrier_id not in seen:
            seen.add(r.carrier_id)
            result.append(r)
    return result


# ── Service ───────────────────────────────────────────────────────────────────

class CarrierProfileService:

    # ── Read ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def list_current(session: AsyncSession, tenant_id: str) -> list[ProfileRow]:
        """Latest version per carrier for this tenant."""
        return await _all_latest(session, tenant_id)

    @staticmethod
    async def get_with_history(
        session: AsyncSession, tenant_id: str, carrier_id: str
    ) -> tuple[ProfileRow | None, list[ProfileRow]]:
        """(current, history) — history newest-first, current excluded."""
        all_rows = list(
            (
                await session.execute(
                    select(ProfileRow)
                    .where(
                        col(ProfileRow.tenant_id) == tenant_id,
                        col(ProfileRow.carrier_id) == carrier_id,
                    )
                    .order_by(desc(col(ProfileRow.created_at)))
                )
            )
            .scalars()
            .all()
        )
        if not all_rows:
            return None, []
        return all_rows[0], all_rows[1:]

    @staticmethod
    async def get_latest(
        session: AsyncSession, tenant_id: str, carrier_id: str
    ) -> ProfileRow | None:
        return await _latest_for(session, tenant_id, carrier_id)

    # ── Write (always creates a new version row) ──────────────────────────────

    @staticmethod
    async def create_version(
        session: AsyncSession,
        ctx: Ctx,
        carrier_id: str,
        data: dict[str, Any],
        *,
        source: str = SOURCE_HUMAN_EDIT,
    ) -> ProfileRow:
        """Human edit: create a new version row from the supplied data dict.
        Chains ``supersedes_version_id`` to the previous latest row."""
        prev = await _latest_for(session, ctx.tenant_id, carrier_id)
        row = ProfileRow(
            tenant_id=ctx.tenant_id,
            carrier_id=carrier_id,
            carrier_name=data.get("carrier_name", carrier_id),
            class_codes_accepted=data.get("class_codes_accepted", []),
            class_codes_excluded=data.get("class_codes_excluded", []),
            states_licensed=data.get("states_licensed", []),
            premium_band=data.get("premium_band", {}),
            submission_requirements=data.get("submission_requirements", {}),
            severity_ceiling=data.get("severity_ceiling", {}),
            appetite_confidence=data.get("appetite_confidence", "medium"),
            appetite_last_updated=data.get("appetite_last_updated"),
            historical_hit_rate_this_class=float(
                data.get("historical_hit_rate_this_class", 0.5)
            ),
            lines_written=data.get("lines_written", []),
            notes=data.get("notes"),
            form_metadata=data.get("form_metadata", {}),
            gap_policy=data.get("gap_policy", {}),
            supersedes_version_id=prev.version_id if prev else None,
            created_by=ctx.user_id,
            source=source,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    @staticmethod
    async def refresh_metadata(
        session: AsyncSession,
        ctx: Ctx,
        carrier_id: str,
        dto: MetadataRefreshDTO,
    ) -> ProfileRow:
        """CI-03 narrow write path (FR-4).

        Only ``appetite_confidence`` and ``appetite_last_updated`` are updated.
        Every other field is copied verbatim from the current version.
        The DTO type enforces this structurally — no runtime check needed.
        """
        prev = await _latest_for(session, ctx.tenant_id, carrier_id)
        if prev is None:
            raise ValueError(
                f"no carrier profile found for carrier_id={carrier_id!r} "
                f"tenant={ctx.tenant_id!r} — cannot refresh metadata"
            )
        row = ProfileRow(
            tenant_id=prev.tenant_id,
            carrier_id=prev.carrier_id,
            carrier_name=prev.carrier_name,
            class_codes_accepted=prev.class_codes_accepted,
            class_codes_excluded=prev.class_codes_excluded,
            states_licensed=prev.states_licensed,
            premium_band=prev.premium_band,
            submission_requirements=prev.submission_requirements,
            severity_ceiling=prev.severity_ceiling,
            appetite_confidence=dto.appetite_confidence,
            appetite_last_updated=dto.appetite_last_updated,
            historical_hit_rate_this_class=prev.historical_hit_rate_this_class,
            lines_written=prev.lines_written,
            notes=prev.notes,
            form_metadata=prev.form_metadata,
            gap_policy=prev.gap_policy,
            supersedes_version_id=prev.version_id,
            created_by=ctx.user_id,
            source=SOURCE_CI,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    # ── Seed importer ─────────────────────────────────────────────────────────

    @staticmethod
    async def seed_from_json(
        session: AsyncSession,
        tenant_id: str,
        profiles: list[CarrierProfile],
        *,
        gap_policy_overrides: dict[str, dict[str, str]] | None = None,
    ) -> list[ProfileRow]:
        """One-time importer: inserts a SEED version row for every profile in
        the JSON panel that doesn't already have any row for this tenant.
        Idempotent — re-running after initial seed is a no-op per carrier.

        ``gap_policy_overrides`` maps carrier_id -> gap_policy dict so the
        hardcoded assembly.py policy can be migrated here on first seed.
        """
        gap_overrides = gap_policy_overrides or {}
        seeded: list[ProfileRow] = []
        for p in profiles:
            existing = await _latest_for(session, tenant_id, p.carrier_id)
            if existing is not None:
                continue  # already seeded — idempotent
            row = ProfileRow(
                tenant_id=tenant_id,
                carrier_id=p.carrier_id,
                carrier_name=p.carrier_name,
                class_codes_accepted=list(p.class_codes_accepted),
                class_codes_excluded=list(p.class_codes_excluded),
                states_licensed=list(p.states_licensed),
                premium_band={
                    "min": p.premium_band.min,
                    "max": p.premium_band.max,
                },
                submission_requirements={
                    "min_loss_run_years": p.submission_requirements.min_loss_run_years,
                    "required_documents": list(p.submission_requirements.required_documents),
                    "acceptance_window_days": p.submission_requirements.acceptance_window_days,
                },
                severity_ceiling={
                    "max_single_claim_incurred": p.severity_ceiling.max_single_claim_incurred
                },
                appetite_confidence=p.appetite_confidence,
                appetite_last_updated=None,
                historical_hit_rate_this_class=p.historical_hit_rate_this_class,
                lines_written=list(p.lines_written),
                notes=p.notes or None,
                form_metadata={},
                gap_policy=gap_overrides.get(p.carrier_id, {}),
                supersedes_version_id=None,
                created_by="system:seed",
                source=SOURCE_SEED,
            )
            session.add(row)
            seeded.append(row)
        if seeded:
            await session.commit()
            for r in seeded:
                await session.refresh(r)
        return seeded

    # ── Matching-engine read (DB-first + JSON fallback) ───────────────────────

    @staticmethod
    async def get_profiles_for_matching(
        session: AsyncSession,
        tenant_id: str,
        workflow_n: int,
    ) -> list[CarrierProfile]:
        """Return carrier profiles as frozen dataclasses for the matching engine.

        Tries the DB store first; falls back to JSON if the store is empty for
        this tenant — preserving Market Matching's zero-false-inclusion guarantee
        in all cases (no regression on day one).
        """
        rows = await _all_latest(session, tenant_id)
        if rows:
            return [profile_row_to_carrier(r) for r in rows]
        # Fall back to JSON panel — no regression on empty store.
        return load_carrier_panel(workflow_n)
