# Sample Test Dataset — Quote Comparison & Recommendation

6 scenarios, each simulating carrier response emails (quotes and/or
declinations) arriving after a submission has been shopped via Market
Matching and Package Assembly. Reuses named insureds and carrier
profiles from those two datasets for continuity, plus one new account
(Brightline Facilities Group) built specifically for the trade-off test.

| # | Scenario | Test Purpose | Expected Mode |
|---|---|---|---|
| 01 | Delta Electric (Ironclad + Meridian quote) | Directly comparable quotes, but one is contingent on an open item | Single primary + flagged secondary |
| 02 | Oakwood Apartment Homes (2 property quotes) | Same premium-looking comparison hides a materially different retained-risk profile via deductible differences | Multi-option, explicit trade-off |
| 03 | Summit Roofing (Ironclad quotes, Palmetto declines) | Late declination handling + narrow quote validity window | Single option, urgent |
| 04 | Oakwood Apartment Homes (revised, with inspection subjectivity) | Distinguishing a routine subjectivity from a timeline-critical one | Single quote, timeline-critical flag |
| 05 | Brightline Facilities Group (2 quotes, endorsement trade-off) | Genuine price-vs-coverage-breadth trade-off with no dominant option | Multi-option, explicit trade-off |
| 06 | Continental Freight Carriers (single quote, expiring) | Single-quote urgency handling — tests that comparison logic isn't only useful when there's something to compare | Urgent single-quote alert |

## The three things this dataset is built to catch

1. **"Lower premium" is not the same as "better quote."** Scenarios 02
   and 05 are both built so that the cheaper option is genuinely worse
   on a dimension that matters for that specific account — retained risk
   (Scenario 02) and administrative/coverage-gap risk (Scenario 05). A
   system that defaults to recommending the lowest premium without this
   context will systematically produce bad recommendations on exactly
   the accounts where getting this right matters most.
2. **Subjectivities are not uniform.** Scenario 04 tests that the system
   distinguishes a routine, low-risk subjectivity ("no new claims prior
   to binding") from a genuinely timeline-critical one ("inspection must
   be scheduled within 10 days"). Treating every subjectivity with the
   same flat urgency either causes alert fatigue (everything is
   "urgent") or misses the one that actually matters.
3. **A single quote still needs active management.** Scenario 06 is
   deliberately not a comparison at all — it's a test that the workflow
   doesn't only produce useful output when there's a decision to weigh
   between options. An expiring, unactioned single quote is one of the
   most costly failure modes in this whole vertical (a real, bindable
   quote lapsing because nobody was watching the clock), and it's easy
   to under-build if the workflow is conceived of purely as a
   "comparison" tool.

## Suggested use

Run each scenario's carrier response(s) through the pipeline and check:
(1) whether comparability was assessed correctly (directly comparable vs.
requiring trade-off framing), (2) whether subjectivities were correctly
classified as routine vs. material, and (3) whether timing/urgency was
surfaced appropriately, especially in Scenarios 03 and 06 where a narrow
validity window is the actual story, not the comparison itself.
