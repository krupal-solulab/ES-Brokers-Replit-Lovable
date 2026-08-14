# Rule Engine Interpretation Guide — Endorsement / Mid-Term Change Processing

**Purpose:** same role as every prior interpretation guide. This
workflow combines judgment patterns from three earlier PRDs — Market
Matching's exclusion-vs-unknown distinction, Renewal Management's
material-change detection, and Binder & Policy Issuance's
never-trust-the-carrier-document-by-default discipline — applied to a
new context: changes requested mid-term on an already-bound policy.

---

## The core distinction in this workflow: materiality and appetite-fit are two separate questions

Every rule below ultimately answers one of two different questions, and
conflating them is the most likely implementation mistake:

1. **Is this change big enough to need underwriting judgment, rather
   than routine processing?** (materiality)
2. **Is this change still within what the carrier is willing to write?**
   (appetite-fit)

A change can be material but clearly in-appetite (Scenario 04 — a large
new location, but a location type the carrier already knows and wants).
A change can be small but appetite-uncertain (imagine a minor-sounding
addition of a class code nobody's confirmed). Scenario 02 and Scenario
03 in the sample dataset are deliberately built to be material in
different ways — one on severity/risk grounds, one on pure appetite-
scope grounds — specifically so an implementation can't collapse both
questions into a single "how big is this change" score.

---

## Rule-by-rule interpretation

### EP-01 — Endorsement Request Classification (routine vs. underwriting-review-required)
**What it checks:** does the requested change fall into a category that
can be processed as a standard administrative endorsement, or does it
require the carrier's underwriting team to actively evaluate it?

**Interpretation note:** build this as a **type-based classification
first, then a materiality check within type**, not a single flat
scoring model. Certain change types (adding a scheduled additional
insured, updating a mailing address, correcting a typo in the named
insured) are essentially always routine regardless of magnitude.
Certain other types (limit increases, new operations/class additions,
new locations) are *never* purely routine — even a small-looking version
of these change types (Scenario 04's location addition) still requires
at least a lighter-weight review, distinguishing it from Scenario 01's
fast-track treatment. Do not build a single numeric "materiality score"
that treats all change types on the same scale — the type of change
matters as much as its size.

### EP-02 — Appetite Recheck for Material Changes
**What it checks:** does the requested change touch class, state, or
severity exposure in a way that requires re-checking the carrier's
appetite profile, and — if so — does the change fall clearly within,
clearly outside, or genuinely unknown relative to that profile?

**Interpretation note — this rule has three possible outcomes, not two,
and the third is the one most likely to be built incorrectly.**
- **Clearly within appetite** (Scenario 04 — habitational class, already
  the carrier's known specialty): proceed with standard underwriting
  review, no special appetite flag needed.
- **Clearly outside appetite:** this should be rare for an endorsement
  request (a broker usually wouldn't ask to add an explicitly excluded
  class), but if it happens, treat as a hard stop, consistent with
  Market Matching's MM-01/MM-04 hard-exclusion pattern.
- **Genuinely unknown** (Scenario 03 — a class that appears on neither
  the accepted nor excluded list): this must NOT be defaulted to either
  "probably fine, process it" or "probably excluded, reject it." It
  must be explicitly surfaced as an open question requiring direct
  carrier confirmation. This directly extends the interpretation
  principle already established for Market Matching's MM-04 rule (an
  empty or sparse accepted-list should not be treated as "excludes
  everything not listed") into this new context, and it's the single
  most important judgment call in this entire rule engine to get right.

### EP-03 — Premium Impact Determination
**What it checks:** does the requested change carry additional premium,
and if so, has that amount been confirmed rather than assumed?

**Interpretation note:** the system can reasonably flag whether a change
*type* is typically premium-bearing (limit increases, location
additions, headcount increases on rated classes almost always are;
scheduled additional insured endorsements typically aren't), but it
must never present an assumed premium figure as confirmed. Scenario 06
is built specifically to test that a small-looking change still gets
routed to the carrier for actual pro-rata confirmation rather than
having Coverline estimate and present a number of its own — this is the
same grounding discipline that governed Package Assembly's auto-fill
boundary (PA-02), applied here to financial figures instead of form
fields: never invent a number the carrier hasn't actually confirmed.

### EP-04 — Endorsement Request Composition Accuracy
**What it checks:** does the drafted endorsement request to the carrier
accurately and completely reflect what the retail agent/insured
actually asked for?

**Interpretation note:** straightforward fidelity check, consistent with
Binder & Policy Issuance's BI-01 — the request should be generated
directly from the structured intake of the retail agent's email, not
re-summarized in a way that could drop detail. Scenario 05's discrepancy
(Harborline Logistics missing from the issued endorsement) is a carrier-
side issuance failure, not a request-composition failure — but this
rule exists to make sure the *request itself*, when it was sent,
correctly specified both additional insureds, so that the eventual
reconciliation check (EP-05) has an accurate baseline to compare
against.

### EP-05 — Issued Endorsement Reconciliation
**What it checks:** once the carrier issues the endorsement, does it
match what was actually requested?

**Interpretation note — this rule is a direct extension of Binder &
Policy Issuance's BI-05, and it should be implemented with the same
seriousness.** Scenario 05 tests a specific, realistic failure mode: a
multi-part request (two additional insureds) where the carrier only
processes part of it. This kind of partial fulfillment is easy to miss
if reconciliation only checks "was an endorsement issued" rather than
"does the issued endorsement contain everything that was requested,
item by item." Build this as an item-level check for multi-part
requests, not just a single yes/no "endorsement received" flag.

### EP-06 — Effective Date / Proration Validation
**What it checks:** for premium-bearing mid-term changes, does the
pro-rata calculation basis make sense given the policy's term and the
requested effective date?

**Interpretation note:** this rule's main job in v1 is to ensure the
*correct inputs* (days elapsed, days remaining, total term length) are
surfaced alongside any premium request to the carrier — v1 does not need
to independently calculate the pro-rata premium itself (that's
appropriately the carrier's determination, consistent with EP-03's
never-assume-a-figure discipline), but it should verify that the timing
inputs feeding that eventual calculation are correct and flag anything
unusual (a request effective *before* the current date, a request very
close to policy expiration where a pro-rata amount might be negligible
enough to question whether an endorsement is even the right mechanism
versus waiting for renewal). Scenario 06 is deliberately a "nothing
unusual here" control case — the system should recognize a
straightforward mid-term timing situation as such, not manufacture
false complexity by treating every proration question with the same
elevated scrutiny warranted by a genuine edge case.

---

## Summary — expected outcomes per sample dataset scenario

| Scenario | Rules primarily tested | Classification |
|---|---|---|
| 01 | EP-01 (type-based routine classification) | ROUTINE, fast-track |
| 02 | EP-01 (materiality), EP-02 (severity-risk appetite concern), EP-03 | UNDERWRITING-REVIEW-REQUIRED |
| 03 | EP-02 (three-outcome appetite check — genuine unknown case) | APPETITE UNKNOWN — must confirm with carrier |
| 04 | EP-01 (material but in-appetite), EP-02, EP-03, EP-06 (pro-rata) | MATERIAL, IN-APPETITE, pro-rata required |
| 05 | EP-04 (request fidelity), EP-05 (partial-fulfillment reconciliation) | DISCREPANCY — item-level reconciliation catch |
| 06 | EP-01 (percentage vs. absolute change), EP-03, EP-06 (control case) | ROUTINE, standard pro-rata |
