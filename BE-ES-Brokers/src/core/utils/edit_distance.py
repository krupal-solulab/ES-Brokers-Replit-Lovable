"""Pure-Python normalized Levenshtein edit distance — no external dependencies.

Used for FR-17/FR-21 feedback-loop metrics: comparing a broker-edited draft body
against the LLM-generated original to quantify how much human editing occurred.

Only exposes two public symbols:
  ``levenshtein_distance(a, b) -> int``   — raw character-level Levenshtein distance
  ``normalized_edit_distance(a, b) -> float`` — distance / max(len(a), len(b)),
      0.0 if both strings are empty or identical, 1.0 if fully rewritten.

Space complexity: O(min(|a|,|b|)) via rolling-row DP — safe for draft-length strings
(typically under 5 000 characters; no guard needed for that scale).

No LLM call. No external library. Deterministic (KB06).
"""

from __future__ import annotations


def levenshtein_distance(a: str, b: str) -> int:
    """Standard Wagner-Fischer edit distance, space-optimised to O(min(|a|,|b|)) rows.

    Always computes over the shorter string as the column axis so the rolling
    row is as small as possible."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    # Keep the shorter string on the column axis
    if len(a) < len(b):
        a, b = b, a

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,           # deletion from a
                curr[j - 1] + 1,       # insertion into a
                prev[j - 1] + (ca != cb),  # substitution (0 if chars match)
            )
        prev = curr
    return prev[-1]


def normalized_edit_distance(a: str, b: str) -> float:
    """Levenshtein distance normalised to [0.0, 1.0] by dividing by max length.

    Interpretation:
      0.0  — strings are identical (distance == 0)
      1.0  — fully rewritten (all characters replaced / document length doubled)

    Edge case: if both strings are empty, returns 0.0 (no change, not undefined).
    """
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0.0
    return levenshtein_distance(a, b) / max_len
