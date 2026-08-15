---
name: G2 Carrier Profile Store
description: Architecture decisions and quirks for the versioned CarrierAppetiteProfile store built in G2.
---

## Key decisions

- Table is in `core/models/tables.py` (shared core, not ES-vertical) because it's cross-workflow.
- Service is in `verticals/es/carrier_profile_store.py` — no repository class (KB04).
- Router is at `verticals/es/workflows/carrier_profiles/router.py`, mounted under `/api/es/carrier-profiles`.
- All writes INSERT a new row; nothing is ever mutated (KB05 append-only). `supersedes_version_id` chains versions.
- `MetadataRefreshDTO` is the structural gate for CI-03 — only `appetite_confidence` + `appetite_last_updated` can be passed.

## TEST_DATA_ROOT is unset — JSON panel never seeds

`TEST_DATA_ROOT` env var is empty in this environment. `load_carrier_panel(n)` always returns `[]`.
The auto-seed in `GET /api/es/carrier-profiles` therefore does nothing on day one.
Profiles must be populated via:
1. `POST /api/es/carrier-profiles/{carrier_id}` (human edit, SENIOR/ADMIN)
2. `POST /api/es/carrier-profiles/seed` after setting TEST_DATA_ROOT
3. CI suggestion approvals

**Why:** The fixture directory uses spaces (`Data sets/Workflow 1/`) and subdirectory names
(`market_matching_dataset/`) that don't match `Workflow_{n}/test_dataset/` — likely a legacy
naming mismatch. Setting TEST_DATA_ROOT to the correct path fixes this.

## Suggestion approve/dismiss

`POST /{carrier_id}/suggestions/{sid}/approve` scans ALL review items for the tenant, finds the
one whose OutputPackage.payload has matching `suggestion_id` + `carrier_id`, applies
`refresh_metadata()` if `metadata_refresh` is populated, then updates `status` to `APPROVED`
in the stored payload JSON blob.

## Gap policy seeding

CAR-06 (Vantage) had a hardcoded `_CARRIER_POLICY_OVERRIDES = {"CAR-06": {"missing_document_type": "disclose"}}` in assembly.py. That constant was removed in G2. The value is now seeded as `gap_policy` on first seed via `_SEED_GAP_POLICY_OVERRIDES` in the router.
