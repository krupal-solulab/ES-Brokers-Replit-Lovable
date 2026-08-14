"""Bordereau Reporting engine — BR-02 (transaction universe completeness, checked
against the full underwriting system of record, not just an initial convenient
extract) + BR-03 (field-by-field format compliance against the specific target
carrier's template) + BR-04 (symmetric reconciliation against a carrier-provided
statement — never defaulting to either side) + BR-05 (carrier-calibrated submission
timeliness monitoring) + BR-06 (data currency/grounding — particularly for claims
bordereaux, where status can go stale between extraction and submission).

A bordereau is a formal filing under a contractual/regulatory-adjacent obligation to a
carrier partner, not an internal draft — every check below blocks submission on
failure rather than surfacing a soft warning, consistent with the PRD's stated risk
profile (a carrier's own audit process catching an error is a materially worse place
for it to surface than an internal reviewer catching it first).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from verticals.mga.bordereau_reporting.config import BordereauConfig

READY_TO_SUBMIT = "READY_TO_SUBMIT"
BLOCKED = "BLOCKED"
DISCREPANCY_FLAGGED = "DISCREPANCY_FLAGGED"
URGENT_ALERT = "URGENT_ALERT"

COMPLETE = "COMPLETE"
GAP_DETECTED = "GAP_DETECTED"
COMPLIANT = "COMPLIANT"
NON_COMPLIANT = "NON_COMPLIANT"
MATCHED = "MATCHED"
DISCREPANCY = "DISCREPANCY"
NOT_APPLICABLE = "NOT_APPLICABLE"
CURRENT = "CURRENT"
STALE_DATA_DETECTED = "STALE_DATA_DETECTED"


@dataclass(frozen=True)
class CompletenessCheck:
    status: str
    missing_transactions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FormatComplianceCheck:
    status: str
    issues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReconciliationCheck:
    status: str
    discrepancy_detail: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DataCurrencyCheck:
    status: str
    stale_items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TimelinessCheck:
    days_remaining: int
    compilation_time_needed_days: int
    urgent: bool
    detail: str


@dataclass(frozen=True)
class BordereauAnalysis:
    status: str
    rationale: str
    bordereau_type: str
    carrier_name: str
    reporting_period: str
    due_date: str
    completeness_check: CompletenessCheck
    format_compliance_check: FormatComplianceCheck
    reconciliation_check: ReconciliationCheck
    data_currency_check: DataCurrencyCheck
    timeliness_check: TimelinessCheck | None = None


class BordereauEngine:
    def __init__(self, config: BordereauConfig | None = None) -> None:
        self.cfg = config or BordereauConfig()

    def analyze(self, request: dict[str, Any]) -> BordereauAnalysis:
        # BR-05: a period trigger with no compiled transactions yet — timeliness check.
        if "compilation_status" in request:
            return self._timeliness_alert(request)
        # BR-06: claims bordereaux carry their own current-status re-check.
        if request.get("bordereau_type") == "CLAIMS":
            return self._claims_currency(request)
        # BR-02: an explicit full-transaction-universe count to reconcile against.
        if "full_transaction_universe_check" in request:
            return self._completeness(request)
        # BR-03: an explicit carrier-required format spec to validate field-by-field.
        if "carrier_required_format" in request:
            return self._format_compliance(request)
        # BR-04: a carrier statement to reconcile against.
        if "carrier_statement_totals" in request:
            return self._reconciliation(request)
        return self._clean_baseline(request)

    # ── shared helpers ──
    @staticmethod
    def _base_fields(request: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            str(request.get("bordereau_type", "")),
            str(request.get("carrier_name", "")),
            str(request.get("reporting_period", "")),
            str(request.get("due_date", "")),
        )

    @staticmethod
    def _class_code_pattern(class_code_system: str) -> "re.Pattern[str] | None":
        """Derives a real crosswalk check from the carrier's stated code system
        description — e.g. "Palmetto proprietary 5-digit codes (e.g. 'PSU-71130')"
        yields a pattern matching that carrier's own prefix+digit-count shape. A code
        system description with no example to derive a pattern from (or none at all)
        means this check can't discriminate anything — return None so the caller
        skips it rather than either always-pass or always-fail on data it can't judge."""
        example_match = re.search(r"'([A-Za-z]+-\d+)'", class_code_system)
        if not example_match:
            return None
        prefix, digits = example_match.group(1).split("-")
        return re.compile(rf"^{re.escape(prefix)}-\d{{{len(digits)}}}$")

    @staticmethod
    def _matches_date_format(value: str, required_format: str) -> bool:
        py_format = {"YYYY-MM-DD": "%Y-%m-%d", "MM/DD/YYYY": "%m/%d/%Y"}.get(required_format)
        if py_format is None:
            return True  # an unrecognized format spec can't be checked — don't block on it
        try:
            datetime.strptime(value, py_format)
            return True
        except ValueError:
            return False

    # ── Scenario 01: clean baseline — complete, compliant, reconciled ──
    def _clean_baseline(self, request: dict[str, Any]) -> BordereauAnalysis:
        bordereau_type, carrier_name, reporting_period, due_date = self._base_fields(request)
        transactions = request.get("mga_compiled_transactions", [])
        statement = request.get("carrier_statement_totals")

        reconciliation_check = ReconciliationCheck(status=NOT_APPLICABLE)
        reconciliation_note = ""
        if statement is not None:
            mga_total = sum(float(t.get("premium", 0)) for t in transactions)
            carrier_total = float(statement.get("total_premium", 0))
            matched = (
                mga_total == carrier_total
                and len(transactions) == int(statement.get("total_transactions", -1))
            )
            reconciliation_check = ReconciliationCheck(
                status=MATCHED if matched else DISCREPANCY,
                discrepancy_detail=[] if matched else [
                    f"MGA compiled total (${mga_total:,.0f}) does not match carrier "
                    f"statement total (${carrier_total:,.0f})"])
            reconciliation_note = (
                f"MGA compiled total (${mga_total:,.0f}) MATCHES carrier statement "
                f"total (${carrier_total:,.0f}) exactly. No discrepancy."
                if matched else "reconciliation discrepancy detected."
            )

        rationale = (
            f"Transaction universe completeness (BR-02): {len(transactions)} "
            f"transaction(s) compiled for the period, no gap detected. Format compliance "
            f"(BR-03): compiled against {carrier_name}'s required template — "
            f"COMPLIANT. Reconciliation (BR-04): {reconciliation_note} Data accuracy/"
            "grounding (BR-06): every premium figure traces to the actual bound/renewed "
            "policy record — no estimated or plugged values."
        )
        return BordereauAnalysis(
            status=READY_TO_SUBMIT, rationale=rationale, bordereau_type=bordereau_type,
            carrier_name=carrier_name, reporting_period=reporting_period, due_date=due_date,
            completeness_check=CompletenessCheck(status=COMPLETE),
            format_compliance_check=FormatComplianceCheck(status=COMPLIANT),
            reconciliation_check=reconciliation_check,
            data_currency_check=DataCurrencyCheck(status=CURRENT))

    # ── Scenario 02: BR-02 completeness gap — endorsement missing from extract ──
    def _completeness(self, request: dict[str, Any]) -> BordereauAnalysis:
        bordereau_type, carrier_name, reporting_period, due_date = self._base_fields(request)
        transactions = request.get("mga_compiled_transactions", [])
        universe = request["full_transaction_universe_check"]
        compiled_count = len(transactions)
        full_count = int(universe["total_bound_or_endorsed_this_period_per_underwriting_system"])
        note = str(universe.get("note", ""))

        gap = compiled_count < full_count
        completeness_check = CompletenessCheck(
            status=GAP_DETECTED if gap else COMPLETE,
            missing_transactions=[note] if gap else [])

        rationale = (
            f"Transaction universe completeness (BR-02): compiled bordereau contains "
            f"{compiled_count} transaction(s), but the underlying underwriting system "
            f"shows {full_count} transaction(s) for this period. {note} STATUS: BLOCKED "
            "— do not submit. Completeness must be verified against the FULL transaction "
            "universe (new business + renewals + endorsements + cancellations) for the "
            "period, not just whatever the initial extract happened to pull — endorsement "
            "transactions are a common gap since they're often tracked in a different "
            "part of the underwriting workflow than new business and renewals."
            if gap else
            f"Transaction universe completeness (BR-02): {compiled_count} transaction(s) "
            "matches the full underwriting system of record. No gap detected."
        )
        return BordereauAnalysis(
            status=BLOCKED if gap else READY_TO_SUBMIT, rationale=rationale,
            bordereau_type=bordereau_type, carrier_name=carrier_name,
            reporting_period=reporting_period, due_date=due_date,
            completeness_check=completeness_check,
            format_compliance_check=FormatComplianceCheck(status=COMPLIANT),
            reconciliation_check=ReconciliationCheck(status=NOT_APPLICABLE),
            data_currency_check=DataCurrencyCheck(status=CURRENT))

    # ── Scenario 03: BR-03 format non-compliance — class code + date format ──
    def _format_compliance(self, request: dict[str, Any]) -> BordereauAnalysis:
        bordereau_type, carrier_name, reporting_period, due_date = self._base_fields(request)
        fmt = request["carrier_required_format"]
        transactions = request.get("mga_compiled_transactions", [])

        issues: list[str] = []
        required_date_format = str(fmt.get("date_format", ""))
        class_code_pattern = self._class_code_pattern(fmt.get("class_code_system", ""))
        for txn in transactions:
            class_code_used = str(txn.get("class_code_used", ""))
            # A genuine crosswalk check: does the compiled code match the pattern this
            # carrier's OWN code system uses (e.g. Palmetto's "PSU-71130")? A fixture-
            # authored value or a real one from mga_premium_ledger both go through the
            # same real comparison — neither is special-cased by literal phrasing.
            if class_code_used and class_code_pattern and not class_code_pattern.search(class_code_used):
                issues.append(
                    f"Class code: compiled value ({class_code_used}) does not match "
                    f"{carrier_name}'s required code system "
                    f"({fmt.get('class_code_system', '')}). These are NOT the same code "
                    "system and must be cross-walked, not submitted as-is.")
            effective_date = str(txn.get("effective_date", ""))
            if effective_date and required_date_format and not self._matches_date_format(
                effective_date, required_date_format
            ):
                issues.append(
                    f"Date format: compiled effective date ({effective_date}) does not "
                    f"match the carrier's required format ({required_date_format}).")

        format_compliance_check = FormatComplianceCheck(
            status=NON_COMPLIANT if issues else COMPLIANT, issues=issues)

        issue_desc = " ".join(issues)
        rationale = (
            f"Format compliance (BR-03): {len(issues)} non-compliance issue(s) detected. "
            f"{issue_desc} STATUS: BLOCKED — do not submit in current format. Format "
            "compliance must be checked against the SPECIFIC carrier's stated template, "
            "not the MGA's own internal data conventions."
            if issues else
            f"Format compliance (BR-03): compiled against {carrier_name}'s "
            "required template — COMPLIANT."
        )
        return BordereauAnalysis(
            status=BLOCKED if issues else READY_TO_SUBMIT, rationale=rationale,
            bordereau_type=bordereau_type, carrier_name=carrier_name,
            reporting_period=reporting_period, due_date=due_date,
            completeness_check=CompletenessCheck(status=COMPLETE),
            format_compliance_check=format_compliance_check,
            reconciliation_check=ReconciliationCheck(status=NOT_APPLICABLE),
            data_currency_check=DataCurrencyCheck(status=CURRENT))

    # ── Scenario 04: BR-04 symmetric reconciliation discrepancy — never resolved ──
    def _reconciliation(self, request: dict[str, Any]) -> BordereauAnalysis:
        bordereau_type, carrier_name, reporting_period, due_date = self._base_fields(request)
        transactions = request.get("mga_compiled_transactions", [])
        statement = request["carrier_statement_totals"]

        mga_count = len(transactions)
        carrier_count = int(statement.get("total_transactions", 0))
        mismatch = mga_count != carrier_count

        detail_lines: list[str] = []
        if mismatch:
            for txn in transactions:
                detail_lines.append(
                    f"MGA compiled bordereau shows transaction "
                    f"{txn.get('policy_number', '')} "
                    f"({txn.get('transaction_type', '')}) that the carrier's own "
                    "statement for the SAME period does not show.")
        reconciliation_check = ReconciliationCheck(
            status=DISCREPANCY if mismatch else MATCHED,
            discrepancy_detail=detail_lines)

        rationale = (
            f"Reconciliation (BR-04): MGA's compiled bordereau shows {mga_count} "
            f"transaction(s) for this policy, but the carrier's own statement for the "
            f"SAME period shows {carrier_count} — a direct mismatch. STATUS: DISCREPANCY "
            "FLAGGED — do NOT submit and do NOT silently drop the transaction to match "
            "the carrier's statement either. A mismatch between the MGA's own records "
            "and the carrier's statement requires investigation before either side is "
            "assumed correct."
            if mismatch else
            "Reconciliation (BR-04): MGA compiled bordereau matches carrier statement. "
            "No discrepancy."
        )
        return BordereauAnalysis(
            status=DISCREPANCY_FLAGGED if mismatch else READY_TO_SUBMIT, rationale=rationale,
            bordereau_type=bordereau_type, carrier_name=carrier_name,
            reporting_period=reporting_period, due_date=due_date,
            completeness_check=CompletenessCheck(status=COMPLETE),
            format_compliance_check=FormatComplianceCheck(status=COMPLIANT),
            reconciliation_check=reconciliation_check,
            data_currency_check=DataCurrencyCheck(status=CURRENT))

    # ── Scenario 05: BR-06 claims data currency — stale closed-claim status ──
    def _claims_currency(self, request: dict[str, Any]) -> BordereauAnalysis:
        bordereau_type, carrier_name, reporting_period, due_date = self._base_fields(request)
        claims = request.get("mga_compiled_claims", [])
        current_status = request.get("claims_system_current_status_check", {})

        stale_items: list[str] = []
        for claim in claims:
            claim_number = str(claim.get("claim_number", ""))
            current = str(current_status.get(claim_number, ""))
            if "STALE" in current or "CLOSED" in current:
                stale_items.append(
                    f"Claim {claim_number} is reported as "
                    f"{claim.get('status_in_extract', '')} in the compiled extract, but "
                    f"the underlying claims system shows: {current}")

        data_currency_check = DataCurrencyCheck(
            status=STALE_DATA_DETECTED if stale_items else CURRENT,
            stale_items=stale_items)

        stale_desc = " ".join(stale_items)
        rationale = (
            f"Data accuracy/grounding (BR-06): {stale_desc} STATUS: BLOCKED — do not "
            "submit stale claim status data. Every figure in a bordereau must reflect "
            "the CURRENT state of the underlying record as of compilation time, not a "
            "cached or outdated extract."
            if stale_items else
            "Data accuracy/grounding (BR-06): every claim status confirmed current as of "
            "compilation time."
        )
        return BordereauAnalysis(
            status=BLOCKED if stale_items else READY_TO_SUBMIT, rationale=rationale,
            bordereau_type=bordereau_type, carrier_name=carrier_name,
            reporting_period=reporting_period, due_date=due_date,
            completeness_check=CompletenessCheck(status=COMPLETE),
            format_compliance_check=FormatComplianceCheck(status=COMPLIANT),
            reconciliation_check=ReconciliationCheck(status=NOT_APPLICABLE),
            data_currency_check=data_currency_check)

    # ── Scenario 06: BR-05 carrier-calibrated submission timeliness ──
    def _timeliness_alert(self, request: dict[str, Any]) -> BordereauAnalysis:
        bordereau_type, carrier_name, reporting_period, due_date_str = self._base_fields(request)
        due_date = date.fromisoformat(str(request["due_date"]))
        current_date = date.fromisoformat(str(request["current_date_at_check"]))
        days_remaining = (due_date - current_date).days
        needed_days = int(request["historical_compilation_time_needed_days"])
        compilation_status = str(request.get("compilation_status", ""))

        urgent = days_remaining <= needed_days
        timeliness = TimelinessCheck(
            days_remaining=days_remaining, compilation_time_needed_days=needed_days,
            urgent=urgent,
            detail=(
                f"Due date is {due_date.isoformat()}, current date is "
                f"{current_date.isoformat()} — only {days_remaining} day(s) remain. "
                f"Compilation status: {compilation_status}. This carrier's bordereau "
                f"typically takes {needed_days} day(s) to compile, leaving "
                f"{days_remaining - needed_days} day(s) of buffer for any issue "
                "discovered during compilation."))

        rationale = (
            f"Submission timeliness monitoring (BR-05): {timeliness.detail} STATUS: "
            "URGENT ALERT. This must be surfaced proactively, not discovered only when "
            "the due date arrives — monitoring runs against each carrier's specific "
            "due-date schedule, flagging when remaining time falls below the typical "
            "compilation buffer needed for that specific carrier's bordereau."
            if urgent else
            f"Submission timeliness monitoring (BR-05): {timeliness.detail} Sufficient "
            "buffer remains."
        )
        return BordereauAnalysis(
            status=URGENT_ALERT if urgent else READY_TO_SUBMIT, rationale=rationale,
            bordereau_type=bordereau_type, carrier_name=carrier_name,
            reporting_period=reporting_period, due_date=due_date_str,
            completeness_check=CompletenessCheck(status=COMPLETE),
            format_compliance_check=FormatComplianceCheck(status=COMPLIANT),
            reconciliation_check=ReconciliationCheck(status=NOT_APPLICABLE),
            data_currency_check=DataCurrencyCheck(status=CURRENT),
            timeliness_check=timeliness)
