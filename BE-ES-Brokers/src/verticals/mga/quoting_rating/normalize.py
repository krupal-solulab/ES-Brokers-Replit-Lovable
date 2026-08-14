"""Normalizes Submission Triage's raw free-text ``acord.class_code`` / ``acord.states_of_
operation`` extraction values into the bare class code / USPS state-abbreviation shape
``RatingConfig.filed_rate_plans`` is keyed on. Triage never produces these normalized
forms itself (see its own ``_build_row``, which only splits class_code for a human-
readable ``industry`` label) — this is Quoting & Rating's own concern, since it's the
only workflow that needs an exact ``(class_code, state)`` lookup key.

Real ACORD text looks like ``"97047 - Landscaping/Gardening Services"`` for class code,
and one of many shapes for state: ``"South Carolina"``, ``"NC, SC"``,
``"NC, SC, GA, TN, VA (regional long-haul)"`` — full names, abbreviations, or both,
optionally comma-joined for multi-state risks, optionally with a trailing parenthetical
note. A submission naming states this module doesn't recognize is dropped rather than
guessed at (QR-06: never rate a state against another state's exposure by mistake)."""

from __future__ import annotations

import re

_STATE_NAME_TO_ABBR: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_VALID_ABBRS = frozenset(_STATE_NAME_TO_ABBR.values())


def normalize_class_code(raw: str) -> str:
    """``"97047 - Landscaping/Gardening Services"`` -> ``"97047"``. Already-bare codes
    pass through unchanged."""
    return raw.split(" - ", 1)[0].strip() if raw else ""


def normalize_states(raw: str) -> list[str]:
    """Splits a free-text states-of-operation value into a deduplicated list of USPS
    state abbreviations, in the order they first appear. Drops a trailing parenthetical
    note (e.g. ``"(regional long-haul)"``) and any comma-separated token that isn't a
    recognized US state name or abbreviation, rather than guessing."""
    if not raw:
        return []
    text = re.sub(r"\([^)]*\)", "", raw)
    seen: list[str] = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        abbr = token.upper() if token.upper() in _VALID_ABBRS else _STATE_NAME_TO_ABBR.get(token.lower())
        if abbr and abbr not in seen:
            seen.append(abbr)
    return seen
