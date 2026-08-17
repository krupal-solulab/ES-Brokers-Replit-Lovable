---
name: Fixture dataset paths
description: How workflow fixture datasets are located on disk (bundled default, TEST_DATA_ROOT override).
---

Rule: fixture loading resolves through the single shared `fixtures.loader.dataset_dir(n)` — `TEST_DATA_ROOT` (if set) first, then the repo-bundled `BE-ES-Brokers/Data sets/Workflow_<n>/test_dataset` fallback. All scenario/trigger loaders and the carrier-profile fallback import this resolver; never re-implement per-workflow path logic.

**Why:** the old convention required a machine-specific TEST_DATA_ROOT (a Windows path in docs), so static/mock data silently loaded nothing on Replit even when data-mode correctly said "static". The repo folders were also named `Workflow 1..10/<name>_dataset` while code expected `Workflow_10..19/test_dataset` (offset by 9); the folders were renamed to the code convention.

**How to apply:**
- New datasets go in `BE-ES-Brokers/Data sets/Workflow_<N>/test_dataset/` using the code's N (E&S workflows are 10–19), not a 1-based folder number.
- MGA Workflow_1..9 eval datasets were never in the repo — those tests only run with an external TEST_DATA_ROOT and some fail against repo data (expect DB-seeded carrier gap-policy profiles); that predates the path fix.
- No symlink trick needed anymore for dataset tests; setting `TEST_DATA_ROOT="$PWD/Data sets"` works directly.
