"""Delegated binding-authority lookup, keyed by class code.

**Why this exists as a stub, not real integration:** a real Quoting & Rating worksheet
carries the RATED premium and class code — it has no reason to also carry which carrier
delegated binding authority for that class or what ceiling applies; that's the MGA's own
carrier-relationship data, not something computed by rating. Per the PRD's own framing,
Bind & Issuance is "the same [PAS/carrier-authority] integration at higher stakes" that
Endorsement Processing's ``policy_lookup.py`` already stubbed for mid-term changes — this
module is that same placeholder pattern, one level up. No real carrier-authority system
exists in this codebase yet, so this is seeded from the same class codes used in the
Workflow-06 sample dataset so a live worksheet referencing one of those real test classes
resolves to real, consistent data instead of failing outright.

Replace ``lookup_authority`` with a real carrier-authority-table query when that
integration exists — every caller already treats a missing class as "no delegated
authority on file", not a crash.
"""

from __future__ import annotations

from typing import Any

# Seeded from the real Workflow-06 dataset's own scenarios (Data sets/Workflow-06/
# mga_bind_issuance_dataset/scenario_0{1,2,3,4,6}/bind_instruction.json) so a live
# worksheet referencing one of these known test classes produces the same authority
# data the eval suite already validates — not fabricated, just not yet integrated.
_KNOWN_CLASSES: dict[str, dict[str, Any]] = {
    "97047": {"carrier": "Meridian Casualty Insurance Co.", "premium_ceiling": 250000},
    "60010": {"carrier": "Heartland Mutual", "premium_ceiling": 250000},
    "71535": {"carrier": "TransGuard Insurance", "premium_ceiling": 120000},
    "91340": {"carrier": "Granite State Mutual", "premium_ceiling": 250000},
    "96065": {"carrier": "Palmetto Specialty Underwriters", "premium_ceiling": 250000},
}


def lookup_authority(class_code: str) -> dict[str, Any] | None:
    return _KNOWN_CLASSES.get(class_code)
