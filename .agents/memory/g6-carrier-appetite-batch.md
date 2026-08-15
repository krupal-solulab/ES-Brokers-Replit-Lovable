---
name: G6 Carrier Appetite Batch Monitor
description: Architecture for the carrier_appetite_batch ScheduledMonitor added in G6.
---

## What was built

One ScheduledMonitor in `verticals/es/monitors/carrier_appetite_batch.py`:
- `carrier_appetite_batch` — FR-1/FR-4/FR-5/FR-6/CI-01..CI-05

## Flow

1. `discover_live_carriers(session, ctx)` → carriers with real QC declination signals
2. For each carrier: `CarrierAppetiteIntelligencePipeline.run_live(ctx, session, carrier_name)` (KB06)
3. Dispatch on pattern_type:
   - CONFIRMED_CONSISTENT → `CarrierProfileService.refresh_metadata(session, ctx, carrier_id, MetadataRefreshDTO(...))` + CI_METADATA_REFRESHED INFO alert
   - GENUINE_INCONSISTENCY → `DefaultReviewQueueService().enqueue()` + CI_SUGGESTION_CREATED WARN alert
   - INSUFFICIENT_SIGNAL → nothing (correct by spec — expected dominant outcome)

## Key design decisions

**FR-4 structural gate**: MetadataRefreshDTO enforces the two-field-only write at the type level.
The monitor passes the pipeline's own `payload.metadata_refresh` fields through the DTO — 
never recomputes confidence from scratch.

**Why**: compute_metadata_refresh() and the pipeline's package() step both produce these
two fields using the same CI-03 logic; using the pipeline's output (KB06) rather than
re-running compute_metadata_refresh() keeps a single authoritative source.

**Suggestion idempotency**: Checks for existing PENDING_REVIEW ReviewItem for carrier_id
(queries ReviewItemRow + OutputPackageRow to inspect payload.carrier_id) before enqueuing.
Prevents inbox spam on repeated scheduler runs while a suggestion awaits human action.

**Metadata refresh idempotency**: Checks if latest CI profile row was written today
(source == CI_METADATA_REFRESH AND created_at.date() == as_of) before calling refresh_metadata.

## Suggestion approval path (unchanged)

The carrier_profiles/router.py `_find_suggestion()` finds suggestions by scanning
ReviewItem → OutputPackage → payload.suggestion_id + payload.carrier_id.
No new endpoints needed — suggestions from the monitor are found by the same mechanism
as manually-triggered /run-live suggestions.

## FE wiring

`CarrierAppetiteIntelligence` fetches `listMonitorAlerts("carrier_appetite_intelligence", false)`
as `caiBatchAlertsQuery`. Shows a "Scheduled batch status" Panel above the KPI grid when
any alerts exist — CI_METADATA_REFRESHED (green CheckCircle2) and CI_SUGGESTION_CREATED (amber ShieldAlert).
