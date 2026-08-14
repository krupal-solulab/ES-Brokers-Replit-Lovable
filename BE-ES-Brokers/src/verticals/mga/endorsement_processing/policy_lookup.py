"""Delegated-authority / rate-plan lookup, keyed by policy number.

**Why this exists as a stub, not real integration:** per the PRD (Section 4, step 1 and
the End-to-End Workflow), a real mid-term change request email only ever contains
``policy_number``, ``named_insured``, and the requested change itself — a broker does
not (and should not) restate the MGA's own delegated binding-authority ceiling, excluded
classes, or filed rate-plan version in a change-request email. That data lives in the
MGA's own policy admin system (PAS) record for the policy, looked up by policy number —
which is exactly the "trial run for in-force policy record integration" the PRD's header
note flags as this workflow's role before Bind Order & Issuance tackles the same
integration at higher stakes. No real PAS integration exists in this codebase yet, so
this module is a clearly-labeled placeholder for that future lookup, seeded from the
same policy numbers used in the Workflow-04/Workflow-01/Workflow-02 sample datasets so a
live email referencing one of those real test policies resolves to real, consistent data
instead of failing outright.

Replace ``lookup_policy`` with a real PAS query when that integration exists — every
caller already treats a missing policy as "route to manual/unknown", not a crash.
"""

from __future__ import annotations

from typing import Any

# Seeded from the real Workflow-04 dataset's own scenarios (Data sets/Workflow-04/
# mga_endorsement_dataset/scenario_0{1,2,3,4,5,6}/endorsement_request.json) so a live
# email referencing one of these known test policies produces the same authority/rate
# data the eval suite already validates — not fabricated, just not yet PAS-integrated.
_KNOWN_POLICIES: dict[str, dict[str, Any]] = {
    "APX-GL-88410": {
        "delegated_authority": {
            "carrier": "Meridian Casualty Insurance Co.", "class_code": "97047",
            "premium_ceiling": 250000, "current_policy_premium": 19845,
        },
    },
    "APX-GL-96065-B": {
        "delegated_authority": {
            "carrier": "Southern Guard Insurance", "class_code": "61220",
            "premium_ceiling": 250000, "current_policy_premium": 68400,
        },
        "rate_plan_reference": {
            "version": "MS-61220-2027.1", "filed_status": "currently filed and approved",
            "base_rate_per_1000_tiv": 2.15,
        },
    },
    "APX-GL-71535": {
        "delegated_authority": {
            "carrier": "TransGuard Insurance", "class_code": "71535",
            "premium_ceiling": 120000, "current_policy_premium": 91200,
        },
    },
    "APX-GL-55012": {
        "delegated_authority": {
            "carrier": "Granite State Mutual", "class_code_current": "91340",
            "excluded_classes": ["habitational", "roofing - steep slope", "asbestos abatement"],
            "note": "Roofing is explicitly on this carrier's excluded class list for this "
                    "MGA's delegated authority agreement",
        },
    },
    "APX-GL-96065-orig": {
        "delegated_authority": {
            "carrier": "Palmetto Specialty Underwriters", "class_code": "96065",
            "premium_ceiling": 250000, "current_policy_premium": 61500,
        },
        "rate_plan_lookup_result": {
            "version_found": "SC-96065-2026.2",
            "filed_status": "SUPERSEDED - newer version SC-96065-2027.1 filed and "
                            "approved 2027-03-01",
            "note": "Same staleness condition as Quoting & Rating Support's Scenario 06, "
                    "now encountered mid-term rather than at new-business quoting",
        },
    },
}


def lookup_policy(policy_number: str) -> dict[str, Any] | None:
    """Returns the ``delegated_authority``/``rate_plan_reference``/``rate_plan_lookup_result``
    fields for a known policy, or ``None`` if this policy has no record yet (caller should
    route to a manual/unknown-policy review state, not fabricate a ceiling)."""
    return _KNOWN_POLICIES.get(policy_number)
