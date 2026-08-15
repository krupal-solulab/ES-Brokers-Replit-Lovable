"""FR-8: loader for the state_retention_reference table.

Reads a JSON reference file supplied by the operator and upserts rows into
``StateRetentionReference``.  The reference file is a *required discovery
input* — never derived from general knowledge.  When the file is absent or
empty, this function does nothing and the compliance engine returns
``retention_period_years=null`` for all states (current behavior preserved).

Expected file format
--------------------
A JSON object mapping ISO 3166-2 US state codes to a dict with two keys:

  {
    "CA": {
      "retention_period_years": 7,
      "source_citation": "CAL. INS. CODE § 1764.2(a)"
    },
    "TX": {
      "retention_period_years": 5,
      "source_citation": "Tex. Ins. Code § 981.105(b)"
    }
  }

Both keys are required per entry.  Entries missing either key are skipped and
logged as a warning (never silently accepted with a guessed value).

Configuration
-------------
File path is resolved from:
  1. The ``filepath`` argument passed to ``load_from_file()``.
  2. The ``RETENTION_REFERENCE_PATH`` environment variable.
  3. The default location: ``<project_root>/data/state_retention_reference.json``.

Upsert behavior: an existing row for the same ``state`` is updated
(``retention_period_years``, ``source_citation``, ``loaded_from``) — the
operator can re-run the loader after updating the reference file.  The ``id``
and ``created_at`` of the original row are preserved.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from core.models import StateRetentionReference as _Row

_log = logging.getLogger(__name__)

# Default reference file location (relative to the project root).
_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "state_retention_reference.json"


def _resolve_path(filepath: str | Path | None) -> Path:
    if filepath:
        return Path(filepath)
    env = os.getenv("RETENTION_REFERENCE_PATH")
    if env:
        return Path(env)
    return _DEFAULT_PATH


def _load_json(path: Path) -> dict[str, dict] | None:
    """Return parsed dict, or None if the file does not exist or is invalid."""
    if not path.exists():
        _log.debug("state_retention_reference: reference file not found at %s — skipping load", path)
        return None
    try:
        with path.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        _log.warning("state_retention_reference: failed to parse %s (%s) — skipping", path, exc)
        return None


async def load_from_file(
    session: AsyncSession,
    filepath: str | Path | None = None,
) -> int:
    """Load/refresh ``state_retention_reference`` rows from the reference file.

    Returns the number of rows upserted.  Skips malformed entries (logs a
    warning per skipped entry — never silently accepts an incomplete row).
    Returns 0 if the file is absent (no-op, no error — current behavior
    preserved exactly).
    """
    path = _resolve_path(filepath)
    data = _load_json(path)
    if not data:
        return 0

    filename = path.name
    upserted = 0

    for state, entry in data.items():
        if not isinstance(entry, dict):
            _log.warning("state_retention_reference: entry for %r is not a dict — skipping", state)
            continue
        years = entry.get("retention_period_years")
        citation = entry.get("source_citation")
        if not isinstance(years, int) or years <= 0:
            _log.warning(
                "state_retention_reference: entry for %r missing valid retention_period_years"
                " (got %r) — skipping (never guessing)", state, years,
            )
            continue
        if not citation or not isinstance(citation, str):
            _log.warning(
                "state_retention_reference: entry for %r missing source_citation — skipping"
                " (citation is required; a figure without a statutory source cannot be trusted)",
                state,
            )
            continue

        existing = (
            await session.execute(
                select(_Row).where(col(_Row.state) == state)
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.retention_period_years = years
            existing.source_citation = citation
            existing.loaded_from = filename
            session.add(existing)
        else:
            session.add(_Row(
                id=str(uuid4()),
                state=state,
                retention_period_years=years,
                source_citation=citation,
                loaded_from=filename,
            ))
        upserted += 1

    await session.commit()
    if upserted:
        _log.info("state_retention_reference: upserted %d rows from %s", upserted, path)
    return upserted


async def load_all(session: AsyncSession) -> dict[str, tuple[int, str]]:
    """Load all rows from the DB into a plain dict for engine lookup.

    Returns ``{state: (retention_period_years, source_citation)}``.
    Empty dict when the table has no rows (engine returns null for all states
    — current behavior preserved).
    """
    rows = (await session.execute(select(_Row))).scalars().all()
    return {r.state: (r.retention_period_years, r.source_citation) for r in rows}
