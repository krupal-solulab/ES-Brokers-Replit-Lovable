"""Endorsement request extraction — parses a real mid-term-change email into exactly the
three fields a broker's email can actually contain: ``policy_number``, ``named_insured``,
and the requested change itself (``requested_change.type`` + ``.detail``). Everything
else the engine needs (``delegated_authority``, ``rate_plan_reference``) is the MGA's own
policy record, resolved separately via ``policy_lookup.lookup_policy`` — never parsed
from the email (see that module's docstring for why).

Expected email shape (``Label: value`` lines, consistent with every other MGA workflow's
extraction convention)::

    Policy Number: APX-GL-88410
    Named Insured: Riverside Landscaping LLC
    Requested Change: Add HomeGate Property Management as additional insured

The change *type* (one of ``EndorsementConfig``'s known values) is inferred from keywords
in the change description — a broker will never write the literal type string
("additional_insured"), so this mirrors the shared extractor's content-signal approach
rather than expecting an exact enum value in the email itself.
"""

from __future__ import annotations

import re
from typing import Any

# ``Label: value`` line — same shape as the shared extractor's _KV pattern.
_KV = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 /_&()\-\.]{1,60}?)\s*:\s*(\S.*?)\s*$")

# Keyword -> change type, checked in priority order (first hit wins). Mirrors
# EndorsementConfig's material/routine vocabulary — keep in sync with that file.
_TYPE_SIGNALS: list[tuple[str, tuple[str, ...]]] = [
    ("location_addition", ("add a location", "new location", "additional location",
                           "add a facility", "additional facility")),
    ("add_operations_class", ("add operations", "new class of business", "expand into",
                              "add a line of business")),
    ("limit_increase", ("increase the limit", "higher limit", "raise the limit",
                        "increase limits")),
    ("additional_insured", ("additional insured", "add as an insured", "name as insured")),
    ("employee_count_update", ("employee count", "headcount", "number of employees")),
    ("contact_update", ("contact update", "change of contact", "update contact")),
]


def _parse_kv(content: str) -> dict[str, str]:
    """Parse ``Label: value`` lines, folding soft-wrapped continuation lines back into
    the value they belong to. A broker's mail client (or the broker themselves) will
    wrap a long "Requested Change:" value onto a second line with no new "Label:"
    prefix — treating that as a separate unmatched line would silently truncate the
    value mid-sentence (e.g. cutting "...as an additional insured" down to "...as an
    additional"), which then breaks the keyword-based change-type inference below."""
    out: dict[str, str] = {}
    last_key: str | None = None
    for line in content.splitlines():
        m = _KV.match(line)
        if m:
            key = re.sub(r"[^a-z0-9]+", "_", m.group(1).strip().lower()).strip("_")
            out[key] = m.group(2).strip()
            last_key = key
        elif line.strip() and last_key is not None:
            out[last_key] = f"{out[last_key]} {line.strip()}"
        else:
            # A blank line ends the current value's continuation — anything after
            # (a sign-off, "Let us know...", etc.) is prose, not part of the field.
            last_key = None
    return out


def _infer_change_type(detail: str) -> str:
    text = detail.lower()
    for change_type, signals in _TYPE_SIGNALS:
        if any(sig in text for sig in signals):
            return change_type
    # Per EndorsementConfig/MEP-01: an unrecognized type must never default to routine —
    # the engine's own classify() already treats unknown types as MATERIAL, so passing
    # a type string that matches nothing in its config is the correct, safe default.
    return "unspecified_change"


def extract_endorsement_request(email_body: str, email_subject: str | None = None) -> dict[str, Any]:
    """Parse a real endorsement-request email body into the
    ``{policy_number, named_insured, requested_change}`` shape — the only fields a
    broker's email can genuinely supply. Never raises: missing fields come back empty,
    letting the caller decide how to handle an incomplete request rather than guessing."""
    kv = _parse_kv(email_body or "")

    policy_number = (
        kv.get("policy_number") or kv.get("policy") or kv.get("policy_no") or ""
    )
    named_insured = kv.get("named_insured") or kv.get("insured") or ""
    change_detail = (
        kv.get("requested_change") or kv.get("change_requested")
        or kv.get("change") or kv.get("request") or ""
    )
    # Fall back to scanning free-text prose for a change description when the email
    # isn't Label: value structured — take the longest non-header line as a best-effort
    # detail rather than leaving it empty when a human clearly described a real request.
    if not change_detail:
        prose_lines = [
            ln.strip() for ln in (email_body or "").splitlines()
            if ln.strip() and not _KV.match(ln)
        ]
        if prose_lines:
            change_detail = max(prose_lines, key=len)

    new_location_tiv = None
    tiv_match = re.search(r"\$?([\d,]+(?:\.\d+)?)\s*(?:tiv|total insurable value)", change_detail.lower())
    if tiv_match:
        new_location_tiv = float(tiv_match.group(1).replace(",", ""))

    requested_change: dict[str, Any] = {
        "type": _infer_change_type(change_detail),
        "detail": change_detail or "(no change description found in email)",
    }
    if new_location_tiv is not None:
        requested_change["new_location_tiv"] = new_location_tiv

    return {
        "policy_number": policy_number,
        "named_insured": named_insured,
        "requested_change": requested_change,
    }
