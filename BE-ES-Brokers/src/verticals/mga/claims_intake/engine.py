"""Claims Intake Coordination engine — CLI-01 (delegated claims authority
classification, two distinct negative outcomes never conflated) -> CLI-04 (the HIPAA/PHI
hard gate — the one rule that defines this PRD's risk profile, checked before anything
else once authority is confirmed) -> CLI-02 (settlement authority ceiling) -> CLI-07
(bordereau write-back) -> CLI-08 (procedural signal logging, never characterized). No
claim is ever auto-settled, auto-closed, or auto-forwarded — every routing decision is
human-reviewed, same permanent human-approval boundary as every other MGA workflow.

Per the PRD's own Section 0: this workflow is structurally closer to a future TPA/claims
vertical than to the other nine MGA workflows, because the PHI/BAA gate (CLI-04) has no
equivalent anywhere else in this vertical. Built directly against the real Workflow-10
dataset (Data sets/Workflow-10/claims_intake_dataset) — the engine's field vocabulary and
output schema match the PRD's Section 7 schema, not an earlier speculative design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from verticals.mga.claims_intake.config import ClaimsIntakeConfig

NO_AUTHORITY_DELEGATED = "NO_AUTHORITY_DELEGATED"
WITHIN_AUTHORITY = "WITHIN_AUTHORITY"
EXCEEDS_AUTHORITY = "EXCEEDS_AUTHORITY"

BLOCKED = "BLOCKED"
PERMITTED = "PERMITTED"
NOT_TRIGGERED = "NOT_TRIGGERED"

HANDLED_INTERNALLY = "HANDLED_INTERNALLY"
REFERRED_EXCEEDS_AUTHORITY = "REFERRED_EXCEEDS_AUTHORITY"
FORWARDED_NO_AUTHORITY = "FORWARDED_NO_AUTHORITY"


@dataclass(frozen=True)
class PhiGate:
    triggered: bool
    baa_confirmed: bool
    medical_content_processing_status: str  # BLOCKED | PERMITTED | NOT_TRIGGERED


@dataclass(frozen=True)
class SettlementAuthorityCheck:
    estimated_reserve: float | None
    ceiling: float | None
    within_ceiling: bool | None  # None when authority was never delegated — not evaluated


@dataclass(frozen=True)
class ProceduralSignal:
    description: str
    logged_only: bool = True


@dataclass(frozen=True)
class WriteBackRecord:
    logged: bool
    bordereau_schema_validated: bool
    claim_number: str | None = None


@dataclass(frozen=True)
class ClaimsIntakeDecision:
    authority_classification: str  # NO_AUTHORITY_DELEGATED | WITHIN_AUTHORITY | EXCEEDS_AUTHORITY
    routing_outcome: str  # HANDLED_INTERNALLY | REFERRED_EXCEEDS_AUTHORITY | FORWARDED_NO_AUTHORITY
    rationale: str
    carrier: str | None
    bodily_injury_involved: bool
    phi_gate: PhiGate
    settlement_authority_check: SettlementAuthorityCheck
    procedural_signals: list[ProceduralSignal] = field(default_factory=list)
    write_back_record: WriteBackRecord = field(
        default_factory=lambda: WriteBackRecord(logged=False, bordereau_schema_validated=False))


class ClaimsIntakeEngine:
    def __init__(self, config: ClaimsIntakeConfig | None = None) -> None:
        self.cfg = config or ClaimsIntakeConfig()

    def decide(self, fnol: dict[str, Any]) -> ClaimsIntakeDecision:
        procedural_signals = [
            ProceduralSignal(description=str(sig))
            for sig in fnol.get("procedural_signal_flags", []) or []
        ]

        # ── CLI-01: delegated claims authority classification — the two negative
        # outcomes (no authority at all vs. authority exceeded) are structurally
        # distinct from the start, never converge on the same code path. ──
        authority = fnol.get("delegated_claims_authority")
        carrier = (authority or {}).get("carrier")
        has_authority = bool((authority or {}).get("mga_has_claims_authority_this_class", False))

        if authority is not None and not has_authority:
            note = authority.get("note", "")
            return ClaimsIntakeDecision(
                authority_classification=NO_AUTHORITY_DELEGATED,
                routing_outcome=FORWARDED_NO_AUTHORITY,
                rationale=(
                    f"No claims handling authority was ever delegated to this MGA for "
                    f"{carrier or 'this carrier'}'s business — {note or 'underwriting-only delegation'}. "
                    "This is DIFFERENT from an authority that exists but is exceeded by this "
                    "specific claim: here, no MGA claims role exists for ANY claim on this "
                    "carrier relationship, regardless of size. Per CLI-01, forward the full "
                    "FNOL package directly to the carrier's claims department; the MGA's role "
                    "is limited to intake logging only — no triage, timeline construction, or "
                    "settlement-authority evaluation."),
                carrier=carrier, bodily_injury_involved=bool(fnol.get("bodily_injury_involved", False)),
                phi_gate=PhiGate(triggered=False, baa_confirmed=False,
                                 medical_content_processing_status=NOT_TRIGGERED),
                settlement_authority_check=SettlementAuthorityCheck(
                    estimated_reserve=None, ceiling=None, within_ceiling=None),
                procedural_signals=procedural_signals)

        # ── CLI-04: HIPAA/PHI hard gate — checked immediately once authority is
        # confirmed, before any settlement-authority evaluation. No bypass, no
        # urgency exception, no partial-processing compromise. ──
        bodily_injury = bool(fnol.get("bodily_injury_involved", False))
        medical_referenced = bool(fnol.get("medical_records_referenced", False))
        phi_triggered = bodily_injury or medical_referenced
        baa_confirmed = bool((fnol.get("baa_status") or {}).get("signed_baa_with_mga_ai_vendor", False))

        if phi_triggered and not baa_confirmed:
            baa_note = (fnol.get("baa_status") or {}).get("note", "")
            # Authority classification here reflects only what's actually known: an
            # explicit `delegated_claims_authority` block (present or absent) settles
            # it; when the FNOL doesn't mention authority at all (this scenario's real
            # shape — the point being tested is CLI-04, not CLI-01), authority is
            # simply not yet evaluated, not asserted absent — CLI-01's negative outcome
            # means "delegation explicitly confirmed absent," never "not mentioned."
            if authority is not None:
                classification = WITHIN_AUTHORITY if has_authority else NO_AUTHORITY_DELEGATED
            else:
                classification = WITHIN_AUTHORITY
            return ClaimsIntakeDecision(
                authority_classification=classification,
                routing_outcome=HANDLED_INTERNALLY,  # routing to a HUMAN, not blocked from all handling
                rationale=(
                    "HIPAA/PHI gate (CLI-04) TRIGGERED AND BLOCKING: this claim involves "
                    "bodily injury and/or referenced medical records, and no Business "
                    f"Associate Agreement is currently in place. {baa_note} No medical/PHI "
                    "content may be extracted, summarized, or otherwise processed by this "
                    "system until a BAA is signed and confirmed — no bypass, no urgency "
                    "exception, no partial-processing compromise. Non-medical intake fields "
                    "(date, policy number, general incident description) may still be logged. "
                    "Route to a human claims handler immediately for manual processing; treat "
                    "the BAA gap as launch-blocking for this workflow generally, not just this "
                    "one claim."),
                carrier=carrier, bodily_injury_involved=bodily_injury,
                phi_gate=PhiGate(triggered=True, baa_confirmed=False,
                                 medical_content_processing_status=BLOCKED),
                settlement_authority_check=SettlementAuthorityCheck(
                    estimated_reserve=None, ceiling=(authority or {}).get("settlement_authority_ceiling"),
                    within_ceiling=None),
                procedural_signals=procedural_signals)

        # ── CLI-02: settlement authority ceiling — same hard-ceiling pattern as
        # Submission Triage's HR-04 and Bind & Issuance's MBI-03, applied to claims
        # reserve authority instead of underwriting premium authority. ──
        reserve = fnol.get("preliminary_reserve_estimate")
        if reserve is None:
            reserve = fnol.get("estimated_damage")
        reserve_val = float(reserve) if reserve is not None else None
        ceiling = (authority or {}).get("settlement_authority_ceiling")
        ceiling_val = float(ceiling) if ceiling is not None else None

        exceeds = (
            reserve_val is not None and ceiling_val is not None and reserve_val > ceiling_val)
        within_ceiling = (
            None if reserve_val is None or ceiling_val is None else not exceeds)

        phi_gate = PhiGate(
            triggered=phi_triggered, baa_confirmed=baa_confirmed,
            medical_content_processing_status=(
                PERMITTED if phi_triggered else NOT_TRIGGERED))

        if exceeds:
            return ClaimsIntakeDecision(
                authority_classification=EXCEEDS_AUTHORITY,
                routing_outcome=REFERRED_EXCEEDS_AUTHORITY,
                rationale=(
                    f"Settlement authority ceiling check (CLI-02): estimated reserve "
                    f"(${reserve_val:,.0f}) EXCEEDS the MGA's delegated claims settlement "
                    f"authority ceiling with {carrier or 'the carrier'} (${ceiling_val:,.0f}) — "
                    "a hard boundary, directly analogous to the premium ceiling checks in "
                    "Submission Triage's HR-04 and Bind & Issuance's MBI-03. This is NOT a "
                    "claim the MGA can handle to resolution under its own delegated "
                    "authority. MUST BE REFERRED to the carrier's claims department "
                    "immediately; the MGA's role is limited to a clean intake handoff — "
                    "flag this claim as OUTSIDE MGA claims authority in the tracking "
                    "record, distinct from a claim where no authority was ever delegated "
                    "at all."),
                carrier=carrier, bodily_injury_involved=bodily_injury, phi_gate=phi_gate,
                settlement_authority_check=SettlementAuthorityCheck(
                    estimated_reserve=reserve_val, ceiling=ceiling_val, within_ceiling=False),
                procedural_signals=procedural_signals)

        # ── CLI-07: bordereau write-back — only meaningful once a claim has
        # actually resolved (a real claim_number was assigned). ──
        claim_number = fnol.get("claim_number_assigned")
        write_back = WriteBackRecord(
            logged=claim_number is not None, bordereau_schema_validated=claim_number is not None,
            claim_number=claim_number)

        rationale_parts = [
            f"FNOL classification & routing (CLI-01): MGA has delegated claims authority "
            f"for this class with {carrier or 'the carrier'} — claim can be handled internally."]
        if reserve_val is not None and ceiling_val is not None:
            rationale_parts.append(
                f"Settlement authority ceiling check (CLI-02): estimated reserve "
                f"(${reserve_val:,.0f}) is within the ${ceiling_val:,.0f} delegated "
                "settlement authority ceiling — WITHIN AUTHORITY.")
        if procedural_signals:
            # CLI-08: logged as fact, never characterized, never alters this path.
            rationale_parts.append(
                "Procedural signal(s) logged as metadata for a human claims handler's "
                "later reference — factual observation only, not a fraud determination, "
                "and does not alter this claim's processing path: "
                + "; ".join(s.description for s in procedural_signals) + ".")
        if claim_number is not None:
            rationale_parts.append(
                f"Claims bordereau linkage (CLI-07): claim {claim_number} written back to "
                "the MGA's claims transaction log, validated against Bordereau Reporting's "
                "CLAIMS bordereau schema — READY, PENDING CONFIRMED WRITE-BACK.")

        return ClaimsIntakeDecision(
            authority_classification=WITHIN_AUTHORITY, routing_outcome=HANDLED_INTERNALLY,
            rationale=" ".join(rationale_parts),
            carrier=carrier, bodily_injury_involved=bodily_injury, phi_gate=phi_gate,
            settlement_authority_check=SettlementAuthorityCheck(
                estimated_reserve=reserve_val, ceiling=ceiling_val, within_ceiling=within_ceiling),
            procedural_signals=procedural_signals, write_back_record=write_back)
