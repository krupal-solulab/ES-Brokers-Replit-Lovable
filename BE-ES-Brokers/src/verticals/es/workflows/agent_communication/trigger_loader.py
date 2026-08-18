"""Loads Workflow_<n>'s ``trigger_XX/trigger_input.json`` fixtures.

Same precedent as package_assembly's ``scenario_loader.py``: this dataset shape
(``trigger_XX/`` folders holding a single JSON object, not ``submission_*/*.txt``)
doesn't match the shared fixtures loader's glob, so it's workflow-owned. See
DATA_AND_FIXTURES.md's Workflow_12 layout note. Used by the eval suite only —
the live API's ``POST /run`` accepts a trigger object directly in the request
body (PRD FR-2's manually-logged path), it doesn't read fixtures itself.
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
class TriggerInput:
    """One trigger's raw ``trigger_input.json``, unparsed beyond JSON decoding."""

    trigger_ref: str
    data: dict[str, Any]


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
        log.warning("No bundled Mock-Data-ES-Broker dataset for Workflow_%d; returning no triggers.", n)
        return None
    dataset = _MOCK_DATA_ES_BROKER / bundled
    if not dataset.is_dir():
        log.warning("Bundled fixture dataset not found at %s; returning no triggers.", dataset)
        return None
    return dataset


def list_trigger_refs(n: int) -> list[str]:
    """All ``trigger_*`` folder names for ``Workflow_<n>``, sorted."""
    dataset = _dataset_dir(n)
    if dataset is None:
        return []
    return sorted(p.name for p in dataset.glob("trigger_*") if p.is_dir())


def load_trigger(n: int, trigger_ref: str) -> TriggerInput:
    """Loads one trigger's ``trigger_input.json``. Raises ``FileNotFoundError`` if
    the dataset or trigger is missing — a caller asking for a SPECIFIC trigger by
    name wants a loud failure, not a silently empty result."""
    dataset = _dataset_dir(n)
    if dataset is None:
        raise FileNotFoundError(f"TEST_DATA_ROOT not set or Workflow_{n} dataset missing")
    path = dataset / trigger_ref / "trigger_input.json"
    if not path.is_file():
        raise FileNotFoundError(f"no trigger_input.json at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return TriggerInput(trigger_ref=trigger_ref, data=data)
