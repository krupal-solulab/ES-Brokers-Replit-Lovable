---
name: Pipeline Reporting FR-4 and FR-6
description: Stage-event BLOCKED delay attribution and provisional revenue attribution added to pipeline reporting.
---

## FR-4 — Carrier-Attributed Time-to-Placement

**New DB table**: `pipeline_stage_event` (migration `f3a7d1e9c204`, down from `6c3e8afc3e92`).
- Fields: `submission_ref` (plain string, no FK), `stage`, `entered_at`, `exited_at`, `attribution` (CARRIER|BROKER|AGENT).
- Append-only; only `exited_at` may be set after creation.

**Package Assembly wiring** (in `run_live()` only — fixture path has no session):
- BLOCKED result → write new `PipelineStageEvent(stage="package_assembly_blocked", entered_at=now, attribution="BROKER")`.
- READY/READY_WITH_GAP result → find open BLOCKED event (exited_at IS NULL) for same submission_ref, set exited_at=now.

**Reporting engine** (`build_time_to_placement_carrier_attributed(placements, stage_events)`):
- `placements` must include `submission_id` key (added in live_aggregator `_build_time_to_placement_data`).
- Only COMPLETED spans (exited_at set) subtracted — open spans never estimated (KB06).
- If no stage events for tenant: `time_to_placement_carrier_attributed` is empty; raw metric remains.

**Why**: Zero broker-attributed days == raw == attributed (no regression when no BLOCKED spans recorded).

## FR-6 / PR-04 — Revenue Attribution (always provisional)

**Commission config**: `Settings.commission_rates_json` (env var, JSON string `{"CarrierName": 0.12}`).
Per-tenant override via Admin Panel key `"commission_rates_json"` (same format).

**Engine** (`build_revenue_attribution(bound_submissions, commission_config)`):
- `bound_submissions` from BI payloads: prefers `carrier_confirmation.confirmed_terms.premium`,
  falls back to `requested_bind_terms.premium_estimate`. Submissions without either excluded.
- If no rate for carrier: `not_configured=True`, `estimated_commission=None` — never guessed.
- `provisional=True` always — must be confirmed with design partner.

**Schema**: `PipelineReportPayload.revenue_attribution: list[RevenueAttributionOut]` (always present, may be empty).

## FE (LiveReportCard)

- Time-to-placement table gains "Avg. carrier-attributed" column when `time_to_placement_carrier_attributed` is non-empty; color-highlights savings in green.
- Warning banner switches from "NOT computed" to "will appear once events exist" when `delay_excluded=False`.
- Revenue attribution tile appears below time-to-placement when non-empty; clearly labeled PROVISIONAL; "not configured" shown for carriers without a commission rate.

## Alembic note

`6c3e8afc3e92` (carrier_appetite_profile) was a standalone head; `f3a7d1e9c204` now extends it linearly. Run `alembic upgrade head` to apply.
