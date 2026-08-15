---
name: G5 Renewal Trigger Monitor
description: Architecture for the renewal_trigger ScheduledMonitor added in G5.
---

## What was built

One ScheduledMonitor in `verticals/es/monitors/renewal_trigger.py`:
- `renewal_trigger` — FR-1/FR-7/FR-8/FR-9/FR-19

Calls `RenewalRemarketingPipeline.run_live(ctx, session, bind_id)` verbatim (KB06) then
`DefaultReviewQueueService().enqueue()` to persist the review item.
Emits RENEWAL_URGENT_REMARKET (URGENT) MonitorAlert when trigger_level == "URGENT_REMARKET".
Also calls Slack notification (best-effort, never raises) using the same helper functions as the router.

## Key difference from G3/G4

This monitor WRITES new ReviewItem rows (not just reads state). That's intentional — 
the task requires the scheduled process to populate the renewal review queue (FR-19).

## Idempotency pattern

Two upfront queries per monitor run:
1. All binder_issuance OutputPackages → find bound policies + expiration dates
2. All renewal_remarketing OutputPackages → set of bind_ids already with trigger-stage review

Check: `is_comparison_stage == False AND payload.bind_id matches`.
Skip if already reviewed. This gives one pipeline call per bind_id per renewal cycle.

## Expiration date extraction

Imports `_bind_expiration_and_premium` from `live_ingestion.py` (private function, same package).
Logic: prefers `carrier_confirmation.confirmed_terms.expiration_date` over
`requested_bind_terms.expiration_date`. Always assumed-default 12-month term.

## Window config

`get_effective_setting(tenant_id, "renewal_trigger_window_days", 90)` — Admin Panel per-tenant override.
Skip if `days_until < 0` (already expired) or `days_until > window_days` (too far out).

## URGENT_REMARKET alert

entity_ref = bind_id (same as `row.submission_id` in renewal_remarketing ReviewItems).
Emitted exactly when the pipeline runs (idempotency ensures once per cycle).
FE: `a.entity_ref === row.submission_id` in queue badge filter;
`a.entity_ref === selectedId || a.entity_ref === payload.bind_id` in detail card filter.

## Slack notification

Uses `resolve_channel_id + try_notify_slack` from `core.ingestion.slack_writeback` directly —
does NOT import from router.py (avoids circular dependency).

## FE wiring

`RenewalRemarketing` fetches `listMonitorAlerts("renewal_remarketing", false)` as `rrMonitorAlertsQuery`.
Queue badge: ShieldAlert + "scan alert" shown per item when any alert entity_ref matches row.submission_id.
`LiveRenewalCard` accepts `monitorAlerts?: MonitorAlert[]` prop; renders RENEWAL_URGENT_REMARKET
alerts in blue `border-primary/30 bg-primary/5` panel above the comparison section (FR-8/FR-22).
