"""Fixtures loader — turns ``TEST_DATA_ROOT/Workflow_<N>/test_dataset`` into
``Submission`` + ``list[Document]`` for the dev seed script and workflow eval tests.

Rules (DATA_AND_FIXTURES.md):
- Never hardcode fixtures in workflow code — always go through this loader.
- Filenames drive document classification (``acord_application`` → ACORD, etc.).
- ``TEST_DATA_ROOT`` is config-driven; if the path is missing we warn and return ``[]``
  (never crash) so the app/tests run without the dataset present.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from core.common.enums import DocumentKind, Vertical
from core.config import get_settings
from core.models import Document, Submission

log = logging.getLogger(__name__)

# Filename-stem → DocumentKind. Extend as new document types appear in datasets.
_KIND_BY_STEM: dict[str, DocumentKind] = {
    "acord_application": DocumentKind.ACORD,
    "loss_run": DocumentKind.LOSS_RUN,
    "financial_statement": DocumentKind.FINANCIALS,
    "sov_report": DocumentKind.SOV,
    "sov": DocumentKind.SOV,
    "email": DocumentKind.EMAIL,
}


def _classify(filename: str) -> DocumentKind:
    return _KIND_BY_STEM.get(Path(filename).stem.lower(), DocumentKind.OTHER)


@dataclass
class LoadedSubmission:
    """One sample case: a Submission plus its Documents (unpersisted SQLModel rows)."""

    submission: Submission
    documents: list[Document] = field(default_factory=list)


# Repo-bundled datasets: BE-ES-Brokers/Data sets/Workflow_<n>/test_dataset.
# This makes fixture loading work out of the box in any environment (no
# machine-specific TEST_DATA_ROOT needed); TEST_DATA_ROOT, when set, still
# wins so an external dataset can override the bundled one.
BUNDLED_DATA_ROOT = Path(__file__).resolve().parents[2] / "Data sets"


def dataset_dir(n: int) -> Path | None:
    """Resolve ``Workflow_<n>/test_dataset`` for any fixture loader.

    Tries ``TEST_DATA_ROOT`` first (if configured), then falls back to the
    repo-bundled ``Data sets`` folder. Returns None (warned) when neither has
    the workflow's dataset — callers treat that as "no fixtures".
    """
    roots: list[Path] = []
    configured = get_settings().test_data_root
    if configured:
        roots.append(Path(configured))
    roots.append(BUNDLED_DATA_ROOT)
    for root in roots:
        dataset = root / f"Workflow_{n}" / "test_dataset"
        if dataset.is_dir():
            return dataset
    log.warning(
        "Fixture dataset Workflow_%d/test_dataset not found under %s; returning no fixtures.",
        n,
        " or ".join(str(r) for r in roots),
    )
    return None


# Backwards-compatible private alias (older loaders/tests referenced this name).
_dataset_dir = dataset_dir


def load_workflow(
    n: int,
    *,
    tenant_id: str = "fixture-tenant",
    vertical: Vertical = Vertical.MGA,
) -> list[LoadedSubmission]:
    """Scan ``Workflow_<n>/test_dataset/submission_*`` → list of LoadedSubmission.

    Each ``submission_XX/`` folder becomes one Submission; each ``.txt`` becomes one
    Document with ``kind`` inferred from the filename. Missing path → ``[]`` (warned).
    """
    dataset = _dataset_dir(n)
    if dataset is None:
        return []

    results: list[LoadedSubmission] = []
    for sub_dir in sorted(dataset.glob("submission_*")):
        if not sub_dir.is_dir():
            continue
        submission = Submission(
            tenant_id=tenant_id,
            vertical=vertical,
            external_ref=sub_dir.name,
            subject=f"Workflow_{n} / {sub_dir.name}",
        )
        documents: list[Document] = []
        for doc_path in sorted(sub_dir.glob("*.txt")):
            try:
                content = doc_path.read_text(encoding="utf-8")
            except OSError as exc:  # unreadable file → skip, don't crash the load
                log.warning("Could not read %s: %s", doc_path, exc)
                continue
            documents.append(
                Document(
                    tenant_id=tenant_id,
                    submission_id=submission.id,
                    kind=_classify(doc_path.name),
                    filename=doc_path.name,
                    uri=str(doc_path),
                    content=content,
                )
            )
        results.append(LoadedSubmission(submission=submission, documents=documents))

    log.info("Loaded %d submissions for Workflow_%d.", len(results), n)
    return results


def load_rules(n: int) -> dict[str, str]:
    """Read a workflow's expected-outcome spec.

    Returns ``{"markdown": <text>}`` from ``Validation_Rules_Test_Dataset.md`` and, if
    present, ``{"json": <text>}`` from a ``rules.json``. Missing path/files → ``{}``.
    """
    dataset = _dataset_dir(n)
    if dataset is None:
        return {}

    out: dict[str, str] = {}
    md = dataset / "Validation_Rules_Test_Dataset.md"
    if md.is_file():
        out["markdown"] = md.read_text(encoding="utf-8")
    else:
        log.warning("No Validation_Rules_Test_Dataset.md in %s.", dataset)

    rules_json = dataset / "rules.json"
    if rules_json.is_file():
        out["json"] = rules_json.read_text(encoding="utf-8")

    return out
