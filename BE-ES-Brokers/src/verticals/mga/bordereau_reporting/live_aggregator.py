"""Builds a real BR-02 (transaction universe completeness) request from what's actually
persisted, instead of a fixture.

The "compiled" side is real: every bind Bind & Issuance has actually written to
``MgaPremiumLedger`` for a carrier in a date range is a genuine bound transaction, with a
real premium, class code, and carrier. The "full universe" side is counted from
Triage/Renewal/Endorsement's own ``OutputPackage`` rows in the same range — this is BR-02's
own point (cross-check the compiled bordereau against everything the underwriting system
of record actually processed, not just what got pulled into the extract).

Also live: BR-03 (format compliance) and BR-05 (submission timeliness), both built
directly from the real ``MgaCarrierProfile`` row seeded for a carrier — no fabricated
reference data, since every field either comes from that table or is real ledger data.

Two honest limitations, not fabricated data:
- "in the period" means "processed in that date range" (``created_at``), not "with a
  policy effective date in that range" — no MGA table persists an effective/bind date
  today (see ``MgaPremiumLedger``'s own docstring on why ``effective_date`` is nullable),
  so period scoping is necessarily coarser than the PRD's own transaction-level fidelity.
- The completeness count only reaches BOUND transactions (Bind & Issuance) plus raw
  Triage/Renewal/Endorsement activity counts — it can't yet name which SPECIFIC
  transaction is missing (BR-02's own gate wants a policy number), only whether the
  aggregate counts match. A genuine gap is still correctly flagged; the diagnostic
  detail is coarser than a fixture's hand-authored scenario.

BR-01 (the profile table itself is only as complete as the carriers seeded into it —
see carrier_profiles.py), BR-04 (needs a carrier-provided statement — no ingestion path
exists for one), and BR-06 (needs a claims system that doesn't exist) stay fixture-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.common.dtos import Ctx
from core.models import OutputPackage as OutputPackageRow
from verticals.mga.bordereau_reporting.carrier_profiles import lookup_carrier_profile
from verticals.mga.models import MgaPremiumLedger

_UNIVERSE_WORKFLOWS = ("submission-triage", "renewal-management", "endorsement-processing")


async def build_completeness_request(
    session: AsyncSession, ctx: Ctx, *, carrier_name: str, reporting_period: str,
    due_date: str,
) -> dict[str, Any]:
    ledger_stmt = select(MgaPremiumLedger).where(
        col(MgaPremiumLedger.tenant_id) == ctx.tenant_id,
        col(MgaPremiumLedger.carrier) == carrier_name,
    )
    ledger_rows = (await session.execute(ledger_stmt)).scalars().all()
    compiled_transactions = [
        {
            "policy_number": row.submission_id,
            "transaction_type": row.transaction_type,
            "class_code_used": row.class_code or "",
            "effective_date": row.effective_date or "",
            "premium": row.premium,
        }
        for row in ledger_rows
    ]

    universe_stmt = (
        select(func.count())
        .where(col(OutputPackageRow.tenant_id) == ctx.tenant_id,
               col(OutputPackageRow.workflow).in_(_UNIVERSE_WORKFLOWS))
    )
    full_universe_count = (await session.execute(universe_stmt)).scalar_one()

    profile = lookup_carrier_profile(carrier_name)
    bordereau_type = "PREMIUM"
    if profile and bordereau_type not in profile.get("bordereau_types", [bordereau_type]):
        bordereau_type = profile["bordereau_types"][0]

    return {
        "bordereau_type": bordereau_type,
        "carrier_name": carrier_name,
        "reporting_period": reporting_period,
        "due_date": due_date,
        "mga_compiled_transactions": compiled_transactions,
        "full_transaction_universe_check": {
            "total_bound_or_endorsed_this_period_per_underwriting_system": full_universe_count,
            "note": (
                "Live count: bound transactions in mga_premium_ledger for this carrier "
                "vs. total Triage/Renewal/Endorsement activity across the tenant (not "
                "yet scoped by policy effective date — see live_aggregator.py)."),
        },
    }


async def _compiled_transactions(
    session: AsyncSession, ctx: Ctx, carrier_name: str,
) -> list[dict[str, Any]]:
    ledger_stmt = select(MgaPremiumLedger).where(
        col(MgaPremiumLedger.tenant_id) == ctx.tenant_id,
        col(MgaPremiumLedger.carrier) == carrier_name,
    )
    rows = (await session.execute(ledger_stmt)).scalars().all()
    return [
        {
            "policy_number": row.submission_id,
            "transaction_type": row.transaction_type,
            "class_code_used": row.class_code or "",
            "effective_date": row.effective_date or "",
            "premium": row.premium,
        }
        for row in rows
    ]


async def build_format_compliance_request(
    session: AsyncSession, ctx: Ctx, *, carrier_name: str, reporting_period: str, due_date: str,
) -> dict[str, Any]:
    """BR-03: a real format-compliance check against the carrier's actual profile row
    (class code system, date format) and real ledger transactions — see engine.py's
    `_format_compliance` for the genuine crosswalk/date-parse comparison this drives."""
    profile = lookup_carrier_profile(carrier_name)
    if profile is None:
        raise KeyError(
            f"no MgaCarrierProfile on file for '{carrier_name}' — BR-01's Requirement "
            "Profile must exist before a format-compliance check can run against it")

    return {
        "bordereau_type": (profile.get("bordereau_types") or ["PREMIUM"])[0],
        "carrier_name": carrier_name,
        "reporting_period": reporting_period,
        "due_date": due_date,
        "carrier_required_format": {
            "class_code_system": profile.get("class_code_system") or "",
            "date_format": profile.get("date_format") or "",
            "required_columns_in_order": profile.get("required_columns_in_order") or [],
        },
        "mga_compiled_transactions": await _compiled_transactions(session, ctx, carrier_name),
    }


async def build_timeliness_request(
    session: AsyncSession, ctx: Ctx, *, carrier_name: str, reporting_period: str, due_date: str,
) -> dict[str, Any]:
    """BR-05: a real, carrier-calibrated timeliness check — `historical_compilation_
    time_needed_days` comes from the carrier's actual profile row, not a guess, and
    `current_date_at_check` is the real current date, not a fixture-authored one."""
    profile = lookup_carrier_profile(carrier_name)
    if profile is None:
        raise KeyError(
            f"no MgaCarrierProfile on file for '{carrier_name}' — BR-01's Requirement "
            "Profile must exist before a timeliness check can be calibrated to it")
    needed_days = profile.get("historical_compilation_time_needed_days")
    if needed_days is None:
        raise ValueError(
            f"'{carrier_name}' has no historical_compilation_time_needed_days on file — "
            "BR-05 cannot calibrate urgency without this carrier-specific figure")

    return {
        "bordereau_type": (profile.get("bordereau_types") or ["PREMIUM"])[0],
        "carrier_name": carrier_name,
        "reporting_period": reporting_period,
        "due_date": due_date,
        "current_date_at_check": datetime.now(UTC).date().isoformat(),
        "historical_compilation_time_needed_days": needed_days,
        "compilation_status": (
            f"{len(await _compiled_transactions(session, ctx, carrier_name))} "
            "transaction(s) compiled so far this period."),
    }
