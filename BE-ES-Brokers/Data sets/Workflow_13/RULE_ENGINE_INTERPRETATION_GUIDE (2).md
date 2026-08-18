# Rule Engine Interpretation Guide — Quote Comparison & Recommendation

**Purpose:** same role as every prior interpretation guide — explains how
to apply each rule correctly, with the specific mistakes that are easy to
make even with the rule definitions in hand.

---

## The core distinction in this workflow: normalization before comparison

Every prior rule engine in this vertical (Market Matching, Package
Assembly) compared a submission against a fixed set of requirements.
This one is different: it compares **two or more offers against each
other**, and offers that look superficially comparable (same limits,
similar premium) can differ in ways that matter enormously once you look
past the headline number. The rules below exist to force that
normalization step before any recommendation is produced.

---

## Rule-by-rule interpretation

### QC-01 — Term normalization for comparability
**What it checks:** do the quotes being compared actually share the same
limits, deductible structure, and coverage scope — or does a premium
comparison require adjustment/caveat first?

**Interpretation note — this is the single most important rule in the
whole workflow, and it's the one most likely to be shortcut under
engineering time pressure.** A naive implementation compares premium
numbers directly and recommends the lowest one. Scenario 02 exists
specifically to catch this: Harbor Specialty's quote is $7,500 cheaper
but carries a $15,000 higher all-perils deductible and a $50,000 higher
wind/hail deductible — meaningfully more retained risk on a coastal
property account. **Before any premium comparison is presented, the
system must first check whether limits, deductibles, and coverage scope
actually match.** If they don't, the output must present the trade-off
explicitly (per QC-06's multi-option mode) rather than a flat "X is
cheaper" statement. Treat any premium comparison between
non-identical terms as incomplete output, not a simplified summary.

### QC-02 — Subjectivity and condition extraction and materiality flagging
**What it checks:** what conditions ("subject to...") does each quote
carry, and which of those conditions could realistically affect
timeline, bindability, or cost — as opposed to routine paperwork?

**Interpretation note:** classify subjectivities into at least two
tiers, not one flat list:
- **Routine:** signed application, no material change in operations,
  no new claims prior to binding — these appear on nearly every quote
  and don't need special handling beyond being listed.
- **Material/timeline-affecting:** anything with its own deadline or
  dependency (a required inspection, a dependency on another policy
  binding first, a requirement for additional underwriting information)
  — these need to be surfaced prominently and should influence how
  urgently the recommendation is communicated downstream.

Scenario 04 is built to test this distinction directly: "SOV confirmed"
and "no new claims" are routine; "satisfactory loss control inspection
to be completed prior to binding, must be scheduled within 10 days" is
not, because it has its own countdown that interacts with the policy's
effective date. A system that flags both with equal weight either
produces alert fatigue or — worse — buries the one that actually
threatens the placement timeline.

### QC-03 — Declination handling and appetite-intelligence signal capture
**What it checks:** when a carrier declines after Market Matching had
included them (or after a broker approached them despite not being the
top match), what should happen with that outcome?

**Interpretation note:** two things need to happen, and they're
different in nature:
1. **Immediate handling:** the declination needs to be reflected clearly
   in the comparison output (fewer options than expected), and if it
   leaves only one viable quote, that should shift the output mode from
   "comparison" to "single option" — this is a mode change, not just a
   data update.
2. **Longer-term signal:** per Scenario 03, a declination that's
   *consistent* with the carrier's already-known appetite profile
   (Palmetto's stated severity ceiling) is a confirming signal, not new
   information — Market Matching's own ranking already correctly
   excluded or down-ranked this carrier for this submission. Log this
   consistency check explicitly; a declination that *contradicts* a
   carrier's stated profile (e.g., a carrier declines something well
   within their stated appetite) is the more interesting signal and
   should be flagged more prominently, since it suggests the Carrier
   Appetite Profile data itself may be stale or wrong. **v1 only logs
   this distinction — it does not act on it** (per the deferred Carrier
   Appetite Intelligence workflow), but the logging should already
   distinguish "expected decline" from "unexpected decline" so that
   future workflow has clean signal to build on.

### QC-04 — Recommendation basis (price vs. terms breadth vs. reliability trade-off)
**What it checks:** when multiple viable quotes exist, what weighting
determines the primary recommendation?

**Interpretation note:** consistent with the Market Matching PRD's own
ranking formula, treat the weighting between price, coverage breadth,
subjectivity burden, and carrier reliability as **configurable, not
fixed** — different brokers and different accounts will reasonably
weigh these differently (a price-sensitive small account vs. a
relationship-sensitive strategic account). Do not hardcode "lowest
premium wins" or any other single-factor default; the sample dataset's
Scenarios 02 and 05 are both built specifically to demonstrate that a
single-factor default produces the wrong recommendation.

### QC-05 — Missing or incomplete quote data handling
**What it checks:** when a carrier's response email doesn't clearly
state a standard field (e.g., no explicit deductible mentioned), how
should the system handle the gap?

**Interpretation note:** this extends the same grounding discipline
established across every Coverline workflow into a new context —
**never assume a missing field matches the submission's requested
terms or a "typical" value.** If a carrier's response doesn't clearly
state the deductible, flag it as "not stated — confirm before
presenting to retail agent" rather than defaulting to whatever was
originally requested in the submission. Carriers frequently quote with
changes from the original ask, and assuming continuity here is exactly
the kind of plausible-sounding inference the Package Assembly PRD's
PA-02 rule already warned against in a different context — the same
discipline applies here.

### QC-06 — Multi-option vs. single-recommendation mode selection
**What it checks:** should the output present one clear "best"
recommendation, or multiple options with an explained trade-off?

**Interpretation note:** default to multi-option mode whenever QC-01
identifies a non-trivial term difference (different deductibles,
different endorsement structure) AND no option is strictly better on
every dimension. Default to single-recommendation mode only when one
option is clearly superior on price, terms, AND subjectivity burden
simultaneously (as in a hypothetical clean case, not represented in this
dataset since every scenario here was deliberately built to have some
nuance) or when there's genuinely only one viable quote (Scenarios 03,
06). **Resist defaulting to single-recommendation mode just because it
produces a cleaner-looking output** — Scenarios 02 and 05 are both
built to test that the system doesn't force a false single winner out
of a genuine trade-off.

### QC-07 — Quote validity window tracking
**What it checks:** how much time remains before each quote's stated
validity expires, and has the broker taken action yet?

**Interpretation note — this rule needs to run independent of whether a
comparison is even relevant.** Scenario 06 tests the case where there's
only one quote (no comparison needed) but the validity window is
genuinely the most urgent thing about the situation. Do not architect
this workflow such that its output is only generated when 2+ quotes
exist to compare — a single quote approaching expiration with no broker
action logged should trigger the same (or higher) priority output as a
multi-quote trade-off. This is the workflow's equivalent of Market
Matching's zero-match handling and Package Assembly's BLOCKED status —
a first-class supported output shape, not an edge case bolted onto the
main comparison logic.

---

## Summary — expected outcomes per sample dataset scenario

| Scenario | Rules primarily tested | Output mode |
|---|---|---|
| 01 | QC-01 (valid comparison), QC-02 (contingent subjectivity), QC-07 (differing validity windows) | Single primary + flagged secondary |
| 02 | QC-01 (comparability failure via deductible mismatch), QC-06 | Multi-option |
| 03 | QC-02 (narrow window), QC-03 (consistent declination) | Single option, urgent |
| 04 | QC-02 (routine vs. material subjectivity classification) | Single quote, timeline-critical |
| 05 | QC-01 (endorsement structure mismatch), QC-04, QC-06 | Multi-option |
| 06 | QC-07 (single-quote urgency, independent of comparison) | Urgent single-quote alert |
