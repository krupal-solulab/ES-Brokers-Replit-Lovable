# Rule Engine Interpretation Guide — Renewal Remarketing

**Purpose:** same role as every prior interpretation guide. This
workflow is the vertical's first to combine logic from three separate
prior PRDs — Market Matching's ranking engine, Quote Comparison's term
normalization, and the exposure/loss-change detection patterns
established in the MGA Renewal Management PRD — into a single decision
about whether to actively shop a renewal at all.

---

## The core distinction in this workflow: there are three different reasons to remarket, not one

Every prior renewal-adjacent rule engine (the MGA Renewal Management
PRD) answered a binary-ish question: renew, renew-with-changes, or
non-renew. This workflow answers a different, prior question: **should
we even actively shop this renewal, and if so, how much effort does
that shopping deserve?** The rules below exist because "remarket: yes"
is not one signal — it can come from three genuinely different
situations, and treating them identically produces either wasted effort
or missed urgency.

---

## Rule-by-rule interpretation

### RR-01 — Exposure Change Detection
### RR-02 — Loss History Change Detection

**What they check:** revenue/headcount/state changes and new-claims/
favorable-resolution patterns since the prior term, directly reusing the
detection logic established in the MGA Renewal Management PRD's RN-01
through RN-08.

**Interpretation note:** these two rules should be implemented as a
near-direct port from the MGA Renewal Management PRD, not re-derived —
the underlying comparison logic (percentage change thresholds, trend
detection) is the same problem shape in both verticals. The main
adaptation needed is data source: in the MGA vertical this compared
against the MGA's own prior-term policy record; here it compares
against the bound policy record from Binder & Policy Issuance
Coordination.

### RR-03 — Incumbent Appetite Recheck
**What it checks:** is the account still within the incumbent carrier's
current appetite, and — new in this workflow — has the incumbent
actually signaled that by responding with renewal terms?

**Interpretation note:** this rule has a dimension the MGA-side
equivalent didn't need: **the incumbent's own responsiveness is itself
a data point**, not just their stated appetite profile. A carrier can
still technically list a class as accepted while quietly deprioritizing
new/renewal business in that class — the clearest real-world signal of
this is silence, which is why RR-07 exists as a related but distinct
rule (see below). Do not treat "check the appetite profile" and "check
whether the incumbent actually responded" as the same check.

### RR-04 — Remarket Trigger Decision
**What it checks:** given the outputs of RR-01, RR-02, RR-03, and RR-07,
should this renewal be actively shopped, and at what level of effort?

**Interpretation note — this is the central judgment call in the entire
workflow, and it must support at least three distinct output states, not
a binary flag:**
- **NO_REMARKET** (Scenarios 01, 06): terms are reasonable relative to
  change, incumbent is responsive, and — per RR-08 — there's no
  historical evidence remarketing this account produces value.
- **LIGHT_REMARKET_CHECK** (Scenario 03): nothing is wrong, but a
  favorable change or a shift into a different competitive size band
  makes a lightweight comparison worth doing. This is meaningfully less
  effort than a full remarket and should be represented as its own
  state, not conflated with either NO_REMARKET or FULL_REMARKET.
- **FULL_REMARKET** (Scenario 02): a material adverse or disproportionate
  signal genuinely warrants confirming the incumbent is still the best
  available option.
- **URGENT_REMARKET** (Scenario 04): triggered by incumbent silence/
  non-response rather than a pricing or exposure signal — this should be
  treated with elevated urgency similar to a timing-critical flag
  elsewhere in the vertical (Quote Comparison's expiring-quote alerts),
  not folded into the same priority tier as FULL_REMARKET, since the
  underlying risk (a genuine coverage lapse) is more severe than "we
  might be leaving some savings on the table."

**Do not build this as a single materiality score that maps onto a
binary remarket/no-remarket flag** — Scenario 03 exists specifically to
prove that the "should we shop this" question has a real middle state
that a binary implementation would collapse incorrectly in either
direction (either over-triggering a full remarket for a mild
opportunity, or under-triggering nothing at all).

### RR-05 — Remarket Execution
**What it checks:** when a remarket is triggered (light, full, or
urgent), how does the system actually go get alternative options?

**Interpretation note:** this is a direct re-invocation of the
Submission Market Matching engine against the account's current
(renewal-time) profile — not a new ranking engine. The only workflow-
specific addition is that the "current profile" being matched now
includes the account's own remarketing history (per RR-08) as
additional context the Market Matching engine wouldn't have had at
original binding. Treat this as calling an existing capability with
updated inputs, not building new matching logic.

### RR-06 — Renewal Terms Comparability
**What it checks:** once remarket alternatives exist, are they genuinely
comparable to the incumbent's renewal offer?

**Interpretation note:** this is a direct re-application of Quote
Comparison's QC-01 discipline (never compare premium alone when limits/
deductibles/terms differ), with one addition specific to this context:
**flag when an alternative quote required a manual underwriting
exception to the carrier's stated appetite profile** (per Scenario 05).
An exception-based quote is real and usable, but it carries different
reliability characteristics than a standard-appetite quote — it may be
harder to renew again next cycle, or may reflect a one-time
accommodation rather than a durable market relationship. This context
should be surfaced explicitly, not silently treated the same as any
other quote.

### RR-07 — Incumbent Non-Response / Silent Non-Renewal Detection
**What it checks:** has the incumbent failed to provide renewal terms
within a reasonable window before expiration, despite broker follow-up?

**Interpretation note:** this is a distinct rule from RR-03 because it's
checking a different thing — RR-03 checks the *carrier's stated
appetite data*, RR-07 checks the *carrier's actual behavior* this
renewal cycle, which can diverge from stated appetite in exactly the
way that matters most (a carrier quietly exiting a class often shows up
as unresponsiveness before it shows up as an updated, formal appetite
profile). The threshold for triggering this rule should be informed by
how much lead time is actually needed to complete a remarket (per
Scenario 04's tight 25-day window) — this needs to fire early enough
that URGENT_REMARKET (per RR-04) still has time to work, not so late
that it's purely diagnostic.

### RR-08 — Relationship Cost / Remarketing History Weighting
**What it checks:** given this specific account's remarketing history,
does shopping it again this cycle have a reasonable expectation of
producing real value?

**Interpretation note — this rule exists specifically to prevent the
system from reflexively remarketing everything "just to check."**
Scenario 06 is built to test that a NO_REMARKET decision on a small,
stable account is grounded in that account's own concrete history (2
consecutive cycles, minimal savings found both times) rather than a
generic small-account heuristic. This distinction matters because a
size-based heuristic would incorrectly suppress remarketing on a small
account that genuinely does have a good reason to shop (imagine a small
account with Scenario 02's severity problem) — the rule needs to weigh
actual historical evidence, not account size as a proxy for it. Where no
remarketing history exists yet (a first renewal cycle), this rule should
have no suppressive effect — it only accumulates value over multiple
cycles.

---

## Summary — expected outcomes per sample dataset scenario

| Scenario | Rules primarily tested | Decision |
|---|---|---|
| 01 | RR-01, RR-02, RR-03 (all clean) | NO_REMARKET |
| 02 | RR-01, RR-02 (adverse), RR-04 (full trigger) | FULL_REMARKET |
| 03 | RR-01 (known/already-priced growth), RR-02 (favorable), RR-04 (light trigger) | LIGHT_REMARKET_CHECK |
| 04 | RR-03, RR-07 (silence detection), RR-04 (urgent trigger) | URGENT_REMARKET |
| 05 | RR-06 (comparability + exception-quote flagging) | Multi-option, contextualized |
| 06 | RR-08 (history-grounded suppression) | NO_REMARKET |
