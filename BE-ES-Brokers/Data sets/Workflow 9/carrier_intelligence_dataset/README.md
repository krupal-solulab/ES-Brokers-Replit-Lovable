# Sample Test Dataset — Carrier Appetite Intelligence Tracking

4 scenarios, deliberately weighted toward **suppression** rather than
action — 3 of 4 scenarios should produce no suggestion at all. This
reflects the workflow's core design constraint: it has been flagged as
the highest scope-creep risk in this vertical since it was first
mentioned in the Market Matching PRD, and this dataset is built to prove
the conservative version works, not to showcase what the system can
detect.

| # | Scenario | Test Purpose | Expected Output |
|---|---|---|---|
| 01 | Palmetto / Roofing, 1 data point | Low-volume noise | **SUPPRESSED** — no output |
| 02 | Meridian / Landscaping, 3 recent consistent declines with stated reason | Genuine appetite-shift pattern | **SUGGESTION GENERATED** — human review required |
| 03 | Ironclad / Roofing, mixed signal with account-specific reason | Normal expected variance, not a class-level shift | **SUPPRESSED** — no output |
| 04 | Coastal Mutual / Habitational, 4/4 consistent | Confirms existing profile is accurate | **METADATA REFRESH ONLY** — confidence/recency updated, no suggestion |

## The one thing this dataset exists to prove

**This workflow should be quiet almost all the time.** If it generates
frequent suggestions, that's a sign the suppression logic (CI-05) is
under-tuned, not a sign the workflow is doing valuable work. Scenario 03
in particular tests the hardest version of this: a carrier that declines
an individual account for account-specific reasons (severity, not
class appetite) should never be treated the same as Scenario 02's
genuine class-level pattern — conflating these two would make the
workflow noisy in exactly the way every prior PRD in this vertical
warned against.

## Suggested use

Run each scenario through the pipeline and confirm: (1) single data
points never produce suggestions regardless of consistency direction,
(2) account-specific decline reasons are distinguished from class-level
appetite statements, (3) suggestions always require explicit human
approval before any Carrier Appetite Profile data changes, and (4) only
confidence/recency metadata — never accepted/excluded class data — is
ever updated automatically.
