---
name: G3 Binder Monitors
description: Architecture and registration pattern for the two binder_issuance ScheduledMonitors added in G3.
---

## What was built

Two ScheduledMonitors in `verticals/es/monitors/binder_issuance.py`:
- `binder_issuance_timeline` — BI-04/FR-10/FR-11; ISSUANCE_OVERDUE URGENT when bind SENT + docs not received + overdue
- `binder_ongoing_obligations` — BI-07/FR-17; OBLIGATION_REMINDER WARN for each obligation where reminder_due is True

Both reuse `recompute_live_state(payload, as_of)` from `coordination_engine` — no independent math (KB06).

## Registration pattern

Monitors must be imported before `get_monitors()` is called (by the arq cron or tests).

`verticals/es/monitors/__init__.py` imports `binder_issuance` as side-effect.
Both `main.py` and `core/jobs/worker.py` import `verticals.es.monitors` at module level.

**Why both:** FastAPI process and arq worker are separate processes. Neither imports the other's entry point.

## entity_ref conventions

- ISSUANCE_OVERDUE: `entity_ref = bind_id` (from `payload.get("bind_id")`)
- OBLIGATION_REMINDER: `entity_ref = f"{bind_id}:{md5(description)[:8]}"` — stable per obligation across runs

The infra builds the full dedupe_key: `{tenant}:{alert_type}:{entity_ref}:{as_of_day}` → one alert per condition per day.

## FE wiring

`LiveBinderCard` in `Workflows.tsx` fetches `listMonitorAlerts("binder_issuance", false)` and filters by `bind_id` prefix.
Shows timeline alerts in blue (`border-primary/30 bg-primary/5`) — distinct from the amber computed `overdue_alert_fired` block.
Dismiss button calls `dismissMonitorAlert(id)` and refetches.
