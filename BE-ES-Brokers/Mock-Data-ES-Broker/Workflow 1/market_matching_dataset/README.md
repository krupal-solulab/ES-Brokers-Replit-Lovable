# Sample Test Dataset — Submission Market Matching

6 fictional carrier appetite profiles + 6 retail agent submissions,
designed to exercise the full matching/ranking logic described in the
PRD's Rule Engine section. All entities, figures, and carriers are
fictional.

## Carrier panel (see `/carrier_profiles`)

| Carrier | Specialty | Premium band | Notes |
|---|---|---|---|
| Meridian Excess & Surplus (CAR-01) | Broad casualty, contractors | $10K-$150K | Strict 5yr loss run requirement |
| Palmetto Specialty Underwriters (CAR-02) | Contractors incl. low-slope roofing | $15K-$250K | Highest historical hit rate for contractors, strict requirements |
| Ironclad Casualty Solutions (CAR-03) | Higher risk tolerance, all roofing types | $20K-$500K | Only 3yr loss run required, accepts higher severity |
| Coastal Mutual Specialty (CAR-04) | Habitational, property | $15K-$300K | Excludes all contractor classes |
| Apex Excess Lines (CAR-05) | Small commercial, broad classes | $1K-$50K | Low premium ceiling excludes larger accounts |
| Vantage Excess Partners (CAR-06) | Large/complex risk only | $100K-$2M | Minimum premium excludes anything smaller regardless of fit |

## Submission scenarios

| # | Submission | Test Purpose | Expected Ranking Output |
|---|---|---|---|
| 01 | Delta Electric Services | Multiple carriers accept the class, but loss run only covers 3 of the panel's varying requirements (5yr for CAR-01/02, 3yr for CAR-03) | **Ironclad (CAR-03) ranks #1** despite lower historical hit-rate — it's the only carrier whose submission requirements are already fully met (3yr loss run). Meridian and Palmetto rank lower with an explicit "additional 2 years of loss history needed" flag, not excluded entirely |
| 02 | Oakwood Apartment Homes | Habitational class — excluded by every contractor-focused carrier | **Single match: Coastal Mutual (CAR-04)**. All others correctly excluded via class-code exclusion (MM-04), not scored low — a clean binary exclusion, tests that excluded carriers don't appear in the ranked list at all |
| 03 | Clearpath Bookkeeping Services | Small account, most carriers' premium floor excludes it | **Single match: Apex Excess Lines (CAR-05)** — the only carrier whose premium band includes a ~$2,400 indicated premium. Tests the low end of the premium-band rule (MM-03) |
| 04 | Continental Freight Carriers | Large excess casualty placement — most carriers' premium ceiling excludes it | **Single match: Vantage Excess Partners (CAR-06)** — tests the high end of the premium-band rule; also the only carrier whose severity ceiling ($2M) accommodates this account's loss history |
| 05 | Summit Roofing Group | Steep-slope roofing with high severity — excluded or over-ceiling everywhere except one carrier | **Single match: Ironclad (CAR-03)** — Meridian and Coastal Mutual exclude roofing/contractors entirely; Palmetto accepts roofing but only low-slope, and its severity ceiling ($150K) is exceeded by this account's $310,000 open claim. Tests both class-scope nuance (steep vs. low slope) and severity ceiling (MM-05) together |
| 06 | GreenLeaf Cultivation Facility | Cannabis cultivation — excluded by every carrier on the panel | **Zero matches.** System must produce a "no market found on current panel" output, not force a low-confidence match, and must flag that diligent-search/declination documentation is still required per compliance rule MM-07 even though no placement resulted |

## What this dataset is specifically testing

Unlike the Triage and Renewal datasets (which test single-recommendation
correctness), this dataset is built to test **ranking and exclusion
logic across a panel**, plus two harder edge cases:

- **Partial-fit ranking (Submission 01):** the system must not simply
  filter carriers into "complete" vs. "incomplete" — it must rank a
  carrier whose requirements are already met above carriers that are
  otherwise a fine class/appetite fit but need more documents, since
  that's the placement-speed value proposition described in the PRD's
  problem statement.
- **True zero-match handling (Submission 06):** the system must resist
  the temptation to force a "best available" match when no real fit
  exists — an incorrect placement recommendation on an excluded class is
  a worse outcome than accurately reporting no market was found, and
  this is the single most important failure mode to catch in the eval
  described in PRD Section 8.

## Suggested use

1. Load all 6 carrier profiles as the matching panel.
2. Run each submission through extraction (reused from the MGA
   Extraction Core) and then the Matching/Ranking Engine.
3. Compare the ranked output against the "Expected Ranking Output"
   column — check both *which carriers appear* and *what order/reasoning*
   they appear in, not just a pass/fail on the top match.
4. Confirm Submission 06 produces an explicit no-match result with the
   diligent-search flag, rather than either an error or a forced
   low-confidence recommendation.
