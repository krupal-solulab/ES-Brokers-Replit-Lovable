---
name: Fixture dataset paths
description: How workflow fixture datasets are located on disk (bundled default, TEST_DATA_ROOT override).
---

Rule: fixture loading resolves through the single shared `fixtures.loader.dataset_dir(n)` — `TEST_DATA_ROOT/Workflow_<n>/test_dataset` (legacy layout, if set) first, then the repo-bundled `BE-ES-Brokers/Mock-Data-ES-Broker/Workflow <n-9>/<name>_dataset` (folders "Workflow 1..10" with a literal space, workflow-specific dataset names). All scenario/trigger loaders and the carrier-profile fallback import this resolver; never re-implement per-workflow path logic.

**Why:** the old convention required a machine-specific TEST_DATA_ROOT (a Windows path in docs), so static/mock data silently loaded nothing on Replit even when data-mode correctly said "static". The repo folders were also named `Workflow 1..10/<name>_dataset` while code expected `Workflow_10..19/test_dataset` (offset by 9); the folders were renamed to the code convention.

**How to apply:**
- New datasets go in `BE-ES-Brokers/Mock-Data-ES-Broker/Workflow <k>/<name>_dataset/` (k = code N − 9) and must be added to `_DATASET_FOLDER_NAMES` in fixtures/loader.py.
- The old `BE-ES-Brokers/Data sets/` folder is a superseded duplicate kept only because the user wants to delete it themselves — never read from it.
- MGA Workflow_1..9 eval datasets were never in the repo — those tests only run with an external TEST_DATA_ROOT and some fail against repo data (expect DB-seeded carrier gap-policy profiles); that predates the path fix.
- No symlink trick needed anymore for dataset tests; setting `TEST_DATA_ROOT="$PWD/Data sets"` works directly.
