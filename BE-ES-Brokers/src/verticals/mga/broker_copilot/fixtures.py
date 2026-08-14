"""Fixtures loader for the Workflow-03 broker-communication dataset — mirrors
``endorsement_processing/fixtures.py``'s discipline (repo-relative dataset path, not
``TEST_DATA_ROOT``, since this lives alongside the repo).

Each ``trigger_NN/trigger_input.json`` is a flat, standalone trigger event (broker name,
recommendation, missing info, etc.) — a different shape from what ``BrokerCopilotService``
normally reads (a real Triage/Renewal ``OutputPackageRow``/``DecisionRow`` looked up by
``submission_id``). ``as_source()`` below adapts one into the other, so a trigger fixture
can stand in for "an existing Triage/Renewal decision" when no real one has been persisted
yet — the same role ``MockConnectorService`` plays for Submission Triage/Renewal Management.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

from core.common.enums import DecisionOutcome

log = logging.getLogger(__name__)

# Repo-relative: src/verticals/mga/broker_copilot/fixtures.py -> repo root is 4 parents up.
_DATASET_DIR = (
    Path(__file__).resolve().parents[4] / "Data sets" / "Workflow-03" / "broker_comm_dataset"
)

# recommendation string (either source workflow's) -> shared DecisionOutcome
_OUTCOME_BY_RECOMMENDATION: dict[str, DecisionOutcome] = {
    "PROCEED": DecisionOutcome.PROCEED,
    "REQUEST_INFO": DecisionOutcome.REQUEST_INFO,
    "DECLINE": DecisionOutcome.DECLINE,
    "RENEW_AS_IS": DecisionOutcome.PROCEED,
    "RENEW_WITH_CHANGES": DecisionOutcome.PROCEED,
    "NON_RENEW": DecisionOutcome.DECLINE,
}

_SOURCE_KEY_BY_LABEL = {
    "Submission Triage": "submission-triage",
    "Renewal Management": "renewal-management",
}


def dataset_dir() -> Path | None:
    return _DATASET_DIR if _DATASET_DIR.is_dir() else None


def load_trigger(name: str) -> dict[str, Any] | None:
    """Load one ``trigger_NN``'s ``trigger_input.json``. None if missing."""
    d = dataset_dir()
    if d is None:
        log.warning("Broker-comm dataset not found at %s", _DATASET_DIR)
        return None
    path = d / name / "trigger_input.json"
    if not path.is_file():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def list_triggers() -> list[str]:
    d = dataset_dir()
    if d is None:
        return []
    return sorted(
        p.name for p in d.iterdir()
        if p.is_dir() and (p / "trigger_input.json").is_file()
    )


def find_trigger_by_id(submission_or_renewal_id: str) -> dict[str, Any] | None:
    """Look up a trigger fixture by its own folder name (e.g. "trigger_05") first —
    the unambiguous match, needed because some triggers deliberately share a
    submission_id/renewal_id with another (e.g. trigger_05's NO_RESPONSE_FOLLOWUP is a
    time-elapsed follow-up on the same submission as trigger_01). Falls back to
    scanning every trigger_NN for one whose submission_id/renewal_id matches, for
    callers that only know the fixture's PRD-sample id (e.g. "SUB-2210", "REN-4402")
    — that scan picks the first folder found and is ambiguous when IDs are shared."""
    direct = load_trigger(submission_or_renewal_id)
    if direct is not None:
        return direct
    for name in list_triggers():
        trigger = load_trigger(name)
        if trigger is None:
            continue
        if trigger.get("submission_id") == submission_or_renewal_id:
            return trigger
        if trigger.get("renewal_id") == submission_or_renewal_id:
            return trigger
    return None


def as_source(
    trigger: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], DecisionOutcome, dict[str, Any]]:
    """Adapt a flat trigger fixture into the ``(detail, row, outcome, decision_details)``
    shape ``BrokerCopilotService._load_source`` normally reads from a real persisted
    decision — same four-tuple contract, fixture-backed instead of DB-backed."""
    recommendation = str(trigger.get("recommendation") or "PROCEED")
    outcome = _OUTCOME_BY_RECOMMENDATION.get(recommendation, DecisionOutcome.PROCEED)

    broker = {
        "name": trigger.get("broker_name") or "—",
        "agency": trigger.get("broker_agency") or "—",
    }
    tenure = trigger.get("broker_relationship_tenure")
    if isinstance(tenure, str):
        # "3 years, moderate volume" / "8 years, high volume, strategic account"
        years_part = tenure.split(",", 1)[0].strip()
        digits = "".join(ch for ch in years_part if ch.isdigit())
        if digits:
            broker["tenureYears"] = int(digits)
        low = tenure.lower()
        if "strategic" in low:
            broker["volumeTier"] = "strategic"
        elif "high" in low:
            broker["volumeTier"] = "high"
        elif "moderate" in low:
            broker["volumeTier"] = "moderate"
        elif "low" in low:
            broker["volumeTier"] = "low"

    missing_info = [
        {"item": m.get("item", ""), "reason": m.get("severity", "")}
        for m in trigger.get("missing_info", []) or []
    ]
    consistency = []
    flagged = trigger.get("flagged_inconsistency")
    if flagged:
        consistency.append({
            "label": flagged.get("rule_triggered", "Consistency check"),
            "detail": flagged.get("description", ""),
            "status": "warn",
        })

    changes = [
        {
            "item": c.get("field", ""),
            "reason": f"{c.get('prior_value', '')} -> {c.get('current_value', '')}"
                      + (f" ({c['pct_change']}%)" if c.get("pct_change") is not None else ""),
            "source": "decision",
        }
        for c in trigger.get("exposure_changes", []) or []
    ]

    detail: dict[str, Any] = {
        "narrative": trigger.get("risk_narrative_summary")
                     or trigger.get("hard_rule_result", {}).get("reason")
                     or "",
        "missingInfo": missing_info,
        "consistency": consistency,
        "changes": changes,
        "broker": broker,
    }
    row: dict[str, Any] = {"insured": trigger.get("named_insured") or "—"}
    decision_details: dict[str, Any] = {
        "consistency_flagged": bool(flagged),
        "needs_info": bool(missing_info),
        "missing_info": bool(missing_info),
        # PRD Section 5.4/FR-11-14: NO_RESPONSE_FOLLOWUP is triggered by time elapsed
        # since a prior communication, not by a fresh Triage/Renewal decision outcome —
        # this fixture shape (no "recommendation" at all) is the only signal for it.
        "no_response_followup": trigger.get("trigger_type") == "NO_RESPONSE_FOLLOWUP",
        "days_until_effective_date": trigger.get("days_until_effective_date"),
    }
    return detail, row, outcome, decision_details


def source_workflow_key(trigger: dict[str, Any]) -> str:
    """Trigger fixtures store the human label ("Submission Triage") — map it to the
    same lowercase-hyphen key (`"submission-triage"`) the API/service use everywhere."""
    label = str(trigger.get("source_workflow") or "")
    return _SOURCE_KEY_BY_LABEL.get(label, "submission-triage")
