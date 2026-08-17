# Sample Test Dataset — Pipeline & Carrier Performance Reporting

4 scenarios, weighted toward testing reporting *integrity* rather than
calculation complexity — the hard part of this workflow isn't computing
percentages, it's resisting the temptation to make incomplete or
low-volume data look cleaner than it is.

| # | Scenario | Test Purpose | Key Behavior |
|---|---|---|---|
| 01 | Q3 clean funnel | Standard complete-data baseline | Straightforward funnel report |
| 02 | Carrier hit-rate, one low-volume carrier | A 100% hit rate on 4 submissions looks better than 63.6% on 22 | Low-volume figures must be annotated, never ranked as if equally reliable |
| 03 | Q3 funnel with a 2-week logging gap | Missing data for one funnel stage | **Must flag the gap explicitly, never interpolate or silently omit it** |
| 04 | Remarketing value with a $0-savings-but-correct-decision case | Collapsing outcomes to a single savings number misrepresents a good decision as a failure | Distinguish "savings identified" from "confirmation value" |

## The throughline connecting this dataset to the very first conversation in this project

Scenario 02 and Scenario 03 are both direct descendants of the very
first critique in this entire engagement — the original Coverline
landing page's fabricated-looking "142 submissions today" dashboard
stats. The concern there was presenting precise-looking numbers without
backing. The concern here is the same failure mode showing up in a
*legitimate* reporting context: a low-volume carrier's 100% hit rate is
technically true and still misleading without a caveat, and a data gap
smoothed into a clean-looking chart is a fabrication even if no single
number was invented. This workflow is the place in the entire Coverline
build where that original lesson matters most operationally, since its
entire output is numbers a brokerage principal will make real decisions
from.

## Suggested use

Run each scenario through the reporting pipeline and check: (1) whether
low-volume figures are annotated rather than presented with false
confidence, (2) whether Scenario 03's data gap is visually and
explicitly flagged rather than silently smoothed over, and (3) whether
Scenario 04's report avoids reducing a genuinely valuable "confirmed the
incumbent was right" outcome to a demoralizing "$0 saved" line item.
