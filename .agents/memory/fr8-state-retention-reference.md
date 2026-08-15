---
name: FR-8 State Retention Reference
description: How the StateRetentionReference table wires into the diligent search compliance engine; loader validation rules; "never guess" enforcement pattern.
---

## Rule
``StateRetentionReference`` is a **global** table (no tenant_id — state law does not vary by tenant). Each row: `state` (unique, indexed), `retention_period_years` (int), `source_citation` (statutory text), `loaded_from` (filename for traceability).

Migration: `a2b3c4d5e6f7` (down from `f3a7d1e9c204`).

## Engine wiring
The "never guess" guarantee is **structurally enforced**, not just a convention:
- `_determine_state_base()` (renamed original `determine_state`) never touches retention.
- `determine_state()` wraps it: if `retention_reference` dict has no entry for the state, returns the base determination unchanged — `retention_period_years` and `retention_source` stay `None`.
- Multi-state: each state is an independent lookup; sibling state values never bleed across.

## Loader validation rules (`retention_reference_loader.py`)
- `retention_period_years` must be an `int > 0` — strings, floats, and zero are rejected and logged; row skipped.
- `source_citation` must be a non-empty string — rows without a citation are skipped (a figure without a statutory source cannot be trusted).
- Absent file: `load_from_file()` returns 0 and does nothing — no exception, no regression.
- Upsert: existing row updated in-place (id + created_at preserved); `loaded_from` updated to current filename.

**Why:** FR-8 maximum-strictness grounding. The retention figure comes from statute, not inference. An incorrect figure on a compliance record is an auditable defect.

## Service / router threading
- `DiligentSearchPipeline` gains `self._retention_reference: dict[str, tuple[int, str]]`.
- Both `run()` and `run_live()` accept a `retention_reference` keyword argument; both pass it through to `determine_state()` calls.
- The router calls `load_all(session)` before every `/run` and `/{item_id}/run-live` call — one DB query, returns dict, passed to pipeline.

## FE
- `StateDeterminationOut` type extended in `diligentSearch.ts` with `retention_source?: string | null`.
- Display: `N years (statutory citation)` when set; `"not loaded for this state"` when null. No FE change needed for the null path — it was already wired.
