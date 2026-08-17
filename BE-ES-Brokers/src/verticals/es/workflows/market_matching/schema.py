"""Pydantic output schema for the Market Matching workflow — shapes what rides in
``OutputPackage.payload`` (the frozen contract's vertical-specific escape hatch).
Not a `core.common` contract; free to evolve with this workflow's FE screen.
"""

from __future__ import annotations

from pydantic import BaseModel


class CarrierMatchOut(BaseModel):
    carrier_id: str
    carrier_name: str
    score: float
    # Deterministic engine score breakdown (KB06): component values (0..1) and
    # the fixed weights they are combined with. None on payloads predating this.
    score_components: dict[str, float] | None = None
    score_weights: dict[str, float] | None = None
    missing: list[str] = []
    flags: list[str] = []
    # Set only when a senior/admin manually overrode a hard exclusion — such a
    # carrier carries NO engine score (score = 0.0) and keeps the rule it broke.
    overridden: bool = False
    override_rule: str | None = None
    override_reason: str | None = None


class ExcludedCarrierOut(BaseModel):
    carrier_id: str
    carrier_name: str
    rule: str
    reason: str


class DiligentSearchOut(BaseModel):
    required: bool
    on_file: int
    compliant: bool
    note: str


class MarketMatchingPayload(BaseModel):
    """The FE Market Matching screen's data needs: a ranked panel, what got
    excluded and why, and the independent compliance flag."""

    submission_id: str | None
    # "MATCHES_FOUND" | "REQUEST_INFO" | "NO_MATCH" — engine-recorded (FR-11).
    # None on payloads predating this field (FE falls back to deriving it).
    outcome: str | None = None
    matches: list[CarrierMatchOut] = []
    excluded: list[ExcludedCarrierOut] = []
    diligent_search: DiligentSearchOut
