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


# Bundled fallback: ships inside the repo so the fixture-driven path works in any
# environment, not just a machine with TEST_DATA_ROOT pointed at the full external
# dataset (see docs/DATA_AND_FIXTURES.md). Keyed by the same workflow_n numbering
# TEST_DATA_ROOT's own Workflow_<n> folders use.
_MOCK_DATA_ES_BROKER = Path(__file__).resolve().parents[2] / "Mock-Data-ES-Broker"
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
        log.warning("No bundled Mock-Data-ES-Broker dataset for Workflow_%d; returning no fixtures.", n)
        return None
    dataset = _MOCK_DATA_ES_BROKER / bundled
    if not dataset.is_dir():
        log.warning("Bundled fixture dataset not found at %s; returning no fixtures.", dataset)
        return None
    return dataset


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
