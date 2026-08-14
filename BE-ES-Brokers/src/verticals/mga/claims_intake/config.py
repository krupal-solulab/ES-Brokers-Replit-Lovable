"""Claims Intake Coordination thresholds — DATA, not code (mirrors every other MGA
workflow's config.py). Per the real Workflow-10 dataset, delegated settlement authority
ceilings and carrier-only/TPA-routing decisions are per-carrier facts carried on each
FNOL's own ``delegated_claims_authority`` block, not a global constant this MGA applies
uniformly — so, unlike other MGA workflows' config modules, there is currently no
cross-claim threshold this engine needs. This class exists as the same extension point
every other workflow's config.py provides, kept empty until a real cross-claim
threshold (e.g. a bordereau-linkage grace period) is identified.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimsIntakeConfig:
    pass
