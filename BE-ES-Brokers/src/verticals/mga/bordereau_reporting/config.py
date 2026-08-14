"""Bordereau Reporting thresholds — DATA, not code (mirrors every other MGA workflow's
config.py).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BordereauConfig:
    # BR-05: a bordereau is an "urgent alert" when the days remaining before the due
    # date fall at or below this carrier's own historical_compilation_time_needed_days
    # (Scenario 06) — never a single generic day-count threshold applied uniformly.
    urgent_buffer_days: int = 0
