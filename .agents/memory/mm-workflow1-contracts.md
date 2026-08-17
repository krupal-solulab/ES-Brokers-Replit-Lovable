---
name: Market Matching workflow contracts
description: Outcome codes, Send handoff, and exclusion-override rules for Workflow 1
---
- Payload carries engine-recorded `outcome` — MATCHES_FOUND / REQUEST_INFO (no readable class code or premium) / NO_MATCH; FE derives only for older payloads. Never present NO_MATCH when info is merely missing.
- Score is deterministic engine output (KB06): matches carry `score_components` + `score_weights`; FE only formats them ("Top fit score", explicitly not a probability). Overridden carriers get score 0 / no engine score.
- "Send" = audited handoff to Package Assembly via `run-from-market-matching` with `carrier_ids` (senior/admin, 422 on empty, one human audit entry). No MM `/send` or `/issue` endpoints exist; nothing ever emails a carrier automatically.
- Exclusion override: senior/admin + mandatory typed reason, audited; moves carrier from excluded → matches with `overridden` metadata.
- PA page hides "Assemble from this selection" when arriving with upstream carriers (packages already created by Send) to avoid duplicates.
- Workflow_10 dataset tests skip without TEST_DATA_ROOT — verify MM engine changes via live API against Briarcliff (`1a0099083e5174e5`; no-ACORD email `1a00e924984ac104`) instead.
