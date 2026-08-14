"""Fixtures loader for the Workflow-10 claims intake dataset — mirrors the other MGA
workflows' fixtures.py discipline (never hardcode fixtures in workflow code). Points at
``Data sets/Workflow-10/claims_intake_dataset``, a real 6-scenario dataset (each
``scenario_NN/fnol_intake.json`` + ``expected_output.txt``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

log = logging.getLogger(__name__)

# Repo-relative: src/verticals/mga/claims_intake/fixtures.py -> repo root is 4 parents up.
_DATASET_DIR = (
    Path(__file__).resolve().parents[4] / "Data sets" / "Workflow-10" / "claims_intake_dataset"
)


def dataset_dir() -> Path | None:
    return _DATASET_DIR if _DATASET_DIR.is_dir() else None


def load_scenario(name: str) -> dict[str, Any] | None:
    """Load one ``scenario_NN``'s ``fnol_intake.json`` from the real dataset."""
    d = dataset_dir()
    if d is None:
        return None
    path = d / name / "fnol_intake.json"
    if not path.is_file():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def list_scenarios() -> list[str]:
    d = dataset_dir()
    if d is None:
        return []
    return sorted(
        p.name for p in d.iterdir()
        if p.is_dir() and (p / "fnol_intake.json").is_file()
    )
