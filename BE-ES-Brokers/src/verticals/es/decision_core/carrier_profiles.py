"""Loads the E&S carrier appetite panel (``carrier_profiles/*.json``) for a
Workflow_<n> dataset. This is E&S-owned fixture access, separate from the shared
``fixtures.loader`` (which only turns ``submission_*/*.txt`` into Submission +
Document — it has no notion of a carrier panel). See DATA_AND_FIXTURES.md's
"Workflow_10 layout note".
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from core.config import get_settings

log = logging.getLogger(__name__)

# Carrier-profile JSON files shipped with the repo — used when TEST_DATA_ROOT
# is absent (dev after a DB reset, CI without fixture mounts, etc.).
# Path: <repo_root>/Mock-Data-ES-Broker/Workflow 1/market_matching_dataset/carrier_profiles/
# __file__ = src/verticals/es/decision_core/carrier_profiles.py  → parents[4] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_BUNDLED_CARRIER_DIR = (
    _REPO_ROOT / "Mock-Data-ES-Broker" / "Workflow 1" / "market_matching_dataset" / "carrier_profiles"
)


@dataclass(frozen=True)
class SeverityCeiling:
    max_single_claim_incurred: float


@dataclass(frozen=True)
class PremiumBand:
    min: float
    max: float


@dataclass(frozen=True)
class SubmissionRequirements:
    min_loss_run_years: int
    required_documents: tuple[str, ...] = ()
    acceptance_window_days: int | None = None


@dataclass(frozen=True)
class CarrierProfile:
    """One carrier's appetite profile. ``ceiling_type`` ("hard" | "soft"), when
    present in the source JSON, is the carrier's own explicit MM-05
    hard/soft severity-ceiling declaration — see matching.py's
    `_severity_is_hard`, which uses it when set and falls back to the
    roofing-class heuristic only when a carrier's profile leaves it unset."""

    carrier_id: str
    carrier_name: str
    class_codes_accepted: tuple[str, ...]
    class_codes_excluded: tuple[str, ...]
    states_licensed: tuple[str, ...]
    premium_band: PremiumBand
    submission_requirements: SubmissionRequirements
    severity_ceiling: SeverityCeiling
    appetite_confidence: str
    historical_hit_rate_this_class: float
    lines_written: tuple[str, ...] = ()
    notes: str = ""
    ceiling_type: str | None = None  # "hard" | "soft" | None (unset -> heuristic)


from fixtures.loader import dataset_dir as _dataset_dir  # shared resolver (bundled fallback)


def _to_profile(raw: dict[str, object]) -> CarrierProfile:
    pb = raw["premium_band"]
    sr = raw["submission_requirements"]
    sc = raw["severity_ceiling"]
    assert isinstance(pb, dict) and isinstance(sr, dict) and isinstance(sc, dict)
    return CarrierProfile(
        carrier_id=str(raw["carrier_id"]),
        carrier_name=str(raw["carrier_name"]),
        class_codes_accepted=tuple(raw.get("class_codes_accepted", []) or []),  # type: ignore[arg-type]
        class_codes_excluded=tuple(raw.get("class_codes_excluded", []) or []),  # type: ignore[arg-type]
        states_licensed=tuple(raw.get("states_licensed", []) or []),  # type: ignore[arg-type]
        premium_band=PremiumBand(min=float(pb["min"]), max=float(pb["max"])),
        submission_requirements=SubmissionRequirements(
            min_loss_run_years=int(sr["min_loss_run_years"]),
            required_documents=tuple(sr.get("required_documents", []) or []),
            acceptance_window_days=sr.get("acceptance_window_days"),
        ),
        severity_ceiling=SeverityCeiling(max_single_claim_incurred=float(sc["max_single_claim_incurred"])),
        appetite_confidence=str(raw.get("appetite_confidence", "medium")),
        historical_hit_rate_this_class=float(raw.get("historical_hit_rate_this_class", 0.5)),  # type: ignore[arg-type]
        lines_written=tuple(raw.get("lines_written", []) or []),  # type: ignore[arg-type]
        notes=str(raw.get("notes", "")),
        ceiling_type=raw.get("ceiling_type"),  # type: ignore[arg-type]
    )


def _locate_carrier_panel_dir(n: int) -> Path | None:
    """Return the carrier_profiles/ directory to load from.

    Priority:
    1. ``TEST_DATA_ROOT/Workflow_{n}/test_dataset/carrier_profiles/``
    2. Repo-bundled ``Mock-Data-ES-Broker/Workflow 1/market_matching_dataset/carrier_profiles/``
       (always present in the repo; no env var needed).

    Returns ``None`` (with a warning) only when neither path exists.
    """
    dataset = _dataset_dir(n)
    if dataset is not None:
        p = dataset / "carrier_profiles"
        if p.is_dir():
            return p
        log.warning("No carrier_profiles/ folder in %s; trying bundled path.", dataset)
    # Bundled fallback — repo-relative, no TEST_DATA_ROOT required.
    if _BUNDLED_CARRIER_DIR.is_dir():
        log.info("Using bundled carrier profiles at %s.", _BUNDLED_CARRIER_DIR)
        return _BUNDLED_CARRIER_DIR
    log.warning(
        "No carrier profiles found for Workflow_%d (TEST_DATA_ROOT=%s, bundled path missing).",
        n,
        get_settings().test_data_root or "unset",
    )
    return None


def load_carrier_panel(n: int) -> list[CarrierProfile]:
    """Load every ``carrier_profiles/*.json`` for ``Workflow_<n>``.

    Missing path/folder -> ``[]`` (warned), matching the shared loader's
    never-crash convention.  Falls back to the repo-bundled profiles when
    ``TEST_DATA_ROOT`` is not set (dev after DB reset, CI without mounts).
    """
    panel_dir = _locate_carrier_panel_dir(n)
    if panel_dir is None:
        return []

    profiles: list[CarrierProfile] = []
    for path in sorted(panel_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read carrier profile %s: %s", path, exc)
            continue
        profiles.append(_to_profile(raw))

    log.info("Loaded %d carrier profiles for Workflow_%d from %s.", len(profiles), n, panel_dir)
    return profiles


async def load_carrier_panel_db(
    session: object,
    tenant_id: str,
    workflow_n: int,
) -> list["CarrierProfile"]:
    """Async DB-first carrier panel load for use from pipeline ``decide()`` methods.

    Tries the DB store (``CarrierProfileService.get_profiles_for_matching``)
    first; falls back to the JSON file panel when the store is empty for this
    tenant.  Import is deferred to avoid a circular-import cycle between
    ``decision_core`` and ``carrier_profile_store``.
    """
    from verticals.es.carrier_profile_store import CarrierProfileService  # deferred

    from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore[attr-defined]

    assert isinstance(session, AsyncSession), "session must be an AsyncSession"
    return await CarrierProfileService.get_profiles_for_matching(
        session, tenant_id, workflow_n  # type: ignore[arg-type]
    )


__all__ = [
    "CarrierProfile",
    "PremiumBand",
    "SeverityCeiling",
    "SubmissionRequirements",
    "load_carrier_panel",
    "load_carrier_panel_db",
]
