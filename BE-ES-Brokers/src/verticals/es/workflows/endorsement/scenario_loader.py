"""Loads Workflow_<n>'s ``scenario_XX/`` endorsement fixtures.

Same mixed-shape precedent as Binder & Issuance's Workflow_14: a pre-issuance
pass ships ``bound_policy_context.json`` (+ ``endorsement_request_email.txt``,
a raw email) and a post-issuance reconciliation pass ships
``endorsement_request_sent.json`` (+ ``carrier_issued_endorsement.txt``).
Doesn't fit ``src/fixtures/loader.py`` — workflow-owned, same precedent as
every prior E&S workflow's loader. See DATA_AND_FIXTURES.md's Workflow_15
layout note.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScenarioBundle:
    scenario_ref: str
    bound_policy_context: dict[str, Any] | None = None
    endorsement_request_email_text: str | None = None
    endorsement_request_sent: dict[str, Any] | None = None
    carrier_issued_endorsement_text: str | None = None


# Bundled fallback: ships inside the repo so the fixture-driven path works in any
# environment, not just a machine with TEST_DATA_ROOT pointed at the full external
# dataset (see docs/DATA_AND_FIXTURES.md). Keyed by the same workflow_n numbering
# TEST_DATA_ROOT's own Workflow_<n> folders use.
_MOCK_DATA_ES_BROKER = Path(__file__).resolve().parents[5] / "Mock-Data-ES-Broker"
_BUNDLED_DATASET_BY_N = {
    10: "Workflow 1/market_matching_dataset",
    11: "Workflow 2/package_assembly_dataset",
    12: "Workflow 3/retail_comm_dataset",
    13: "Workflow 4/quote_comparison_dataset",
    14: "Workflow 5/binder_issuance_dataset",
    15: "Workflow 6/endorsement_dataset",
    16: "Workflow 7/renewal_remarketing_dataset",
    17: "Workflow 8/diligent_search_dataset",
    18: "Workflow 9/carrier_intelligence_dataset",
    19: "Workflow 10/pipeline_reporting_dataset",
}


def _dataset_dir(n: int) -> Path | None:
    root = get_settings().test_data_root
    if root:
        dataset = Path(root) / f"Workflow_{n}" / "test_dataset"
        if dataset.is_dir():
            return dataset
        log.warning("Fixture dataset not found at %s; trying the bundled copy.", dataset)
    bundled = _BUNDLED_DATASET_BY_N.get(n)
    if bundled is None:
        log.warning("No bundled Mock-Data-ES-Broker dataset for Workflow_%d; returning no scenarios.", n)
        return None
    dataset = _MOCK_DATA_ES_BROKER / bundled
    if not dataset.is_dir():
        log.warning("Fixture dataset not found at %s; returning no scenarios.", dataset)
        return None
    return dataset


def list_scenario_refs(n: int) -> list[str]:
    dataset = _dataset_dir(n)
    if dataset is None:
        return []
    return sorted(p.name for p in dataset.glob("scenario_*") if p.is_dir())


def _read_json(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _read_text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def load_scenario(n: int, scenario_ref: str) -> ScenarioBundle:
    """Loads whichever of the four fixture files exist for one scenario.
    Raises ``FileNotFoundError`` if the dataset or scenario folder itself is
    missing — a caller asking for a SPECIFIC scenario wants a loud failure."""
    dataset = _dataset_dir(n)
    if dataset is None:
        raise FileNotFoundError(f"TEST_DATA_ROOT not set or Workflow_{n} dataset missing")
    scenario_dir = dataset / scenario_ref
    if not scenario_dir.is_dir():
        raise FileNotFoundError(f"no scenario folder at {scenario_dir}")

    return ScenarioBundle(
        scenario_ref=scenario_ref,
        bound_policy_context=_read_json(scenario_dir / "bound_policy_context.json"),
        endorsement_request_email_text=_read_text(scenario_dir / "endorsement_request_email.txt"),
        endorsement_request_sent=_read_json(scenario_dir / "endorsement_request_sent.json"),
        carrier_issued_endorsement_text=_read_text(scenario_dir / "carrier_issued_endorsement.txt"),
    )
