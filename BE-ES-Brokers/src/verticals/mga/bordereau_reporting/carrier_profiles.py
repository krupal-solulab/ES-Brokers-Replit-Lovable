"""Seeds real ``MgaCarrierProfile`` rows from the Workflow-09 sample dataset's own two
carriers, so a live bordereau run against a known test carrier resolves to real,
consistent reference data instead of failing outright — same stub-seeded-from-the-
real-dataset pattern as ``endorsement_processing/policy_lookup.py`` and
``bind_issuance/authority_lookup.py``.

This is reference data (carrier onboarding facts: format spec, frequency, due-date
convention), not something any engine computes — a real system would maintain these
rows through an admin/onboarding flow, not this module. Replace/extend with real
carrier data as MGAs onboard; every caller already treats a missing carrier as "no
profile on file," not a crash.
"""

from __future__ import annotations

from typing import Any

# Seeded from Data sets/Workflow-09/bordereau_dataset/scenario_0{1,3,6}/period_context.json
_KNOWN_CARRIERS: dict[str, dict[str, Any]] = {
    "Meridian Casualty Insurance Co.": {
        "bordereau_types": ["PREMIUM", "CLAIMS"],
        "frequency": "monthly",
        "due_date_rule": "15 days after period end",
        "class_code_system": None,
        "date_format": None,
        "required_columns_in_order": None,
        "historical_compilation_time_needed_days": None,
        "accepts_carrier_statement_for_reconciliation": True,
    },
    "Palmetto Specialty Underwriters": {
        "bordereau_types": ["PREMIUM"],
        "frequency": "monthly",
        "due_date_rule": "10 days after period end",
        "class_code_system": "Palmetto proprietary 5-digit codes (e.g. 'PSU-71130')",
        "date_format": "YYYY-MM-DD",
        "required_columns_in_order": [
            "policy_number", "insured_name", "psu_class_code", "transaction_type",
            "effective_date", "gross_premium", "commission_amount", "net_premium",
        ],
        "historical_compilation_time_needed_days": 3,
        "accepts_carrier_statement_for_reconciliation": False,
    },
}


def lookup_carrier_profile(carrier_name: str) -> dict[str, Any] | None:
    return _KNOWN_CARRIERS.get(carrier_name)


def seed_data() -> dict[str, dict[str, Any]]:
    """The full seed table, for a one-time DB population job — see
    ``ensure_carrier_profiles_seeded`` in service.py."""
    return _KNOWN_CARRIERS
