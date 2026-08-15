---
name: G4 Quote Validity Monitor
description: Architecture for the quote_validity_window ScheduledMonitor added in G4.
---

## What was built

One ScheduledMonitor in `verticals/es/monitors/quote_comparison.py`:
- `quote_validity_window` — QC-07/FR-14/FR-15/FR-16/FR-26

Calls `recompute_urgency_from_payload(payload, as_of, threshold)` verbatim (KB06).
Emits QUOTE_VALIDITY_URGENT (URGENT) per urgency_flag returned by the engine.
Emits QUOTE_LAPSED (INFO) once when status == "LAPSED".

## Broker-action guard

"No broker action" = `status == "PENDING_REVIEW"`.
Statuses `PRESENTED`, `REVISION_REQUESTED`, `LAPSED` suppress QUOTE_VALIDITY_URGENT.
LAPSED items receive their own INFO alert path.

## LAPSED "emit once" pattern

The infra dedupe_key includes as_of_day → would emit every day.
Fix: monitor queries DB for existing QUOTE_LAPSED alert with this entity_ref before emitting.
If one already exists (from any prior day), skip.

**Why:** "Emit once" semantics for lapsed alerts require cross-day uniqueness, which the infra's daily dedupe_key does not provide. The pre-check is the correct pattern; the infra handles same-day idempotency on top of it.

## entity_ref conventions

- QUOTE_VALIDITY_URGENT: `entity_ref = f"{item_id}:{quote_id}"` — one alert per (item, quote) per day
- QUOTE_LAPSED: `entity_ref = item_id` — one alert per item (ever)

## Threshold override

`get_effective_setting(tenant_id, "quote_validity_urgency_threshold_days", VALIDITY_URGENCY_THRESHOLD_DAYS)`
No separate env var — uses the Admin Panel settings_override system.

## FE wiring

`QuoteComparison` fetches `listMonitorAlerts("quote_comparison", false)` (qcMonitorAlertsQuery).
Queue badge: "scan alert" + ShieldAlert icon shown per item in the Comparisons panel when any alert matches entity_ref.
`LiveComparisonCard` accepts `monitorAlerts?: MonitorAlert[]` prop; shows scheduled alerts below the existing on-read `urgency_flags` block (FR-22 visual distinction: blue `border-primary/30 bg-primary/5` vs amber computed flags).
