# Rule Engine Interpretation Guide — Pipeline & Carrier Performance Reporting

**Purpose:** same role as every prior guide. Unlike most rule engines in
this project, these "rules" are mostly about metric integrity and
honest presentation rather than classification judgment calls — but
getting them wrong is just as consequential, because this workflow's
entire output is numbers a brokerage principal will act on directly.

---

### PR-01 — Funnel Stage Definition & Attribution
**What it does:** defines exact boundaries between pipeline stages
(submission received → matched → packaged → quoted → compared/selected
→ bound) so counts don't double-count or silently drop records between
stages.

**Interpretation note:** each stage's count should be traceable to a
specific logged event from the workflow that produces it (Market
Matching, Package Assembly, Quote Comparison, Binder & Policy Issuance)
— this is aggregation of existing logs, not new tracking infrastructure,
consistent with how Carrier Appetite Intelligence was scoped to reuse
existing signals rather than collect new ones.

### PR-02 — Carrier Hit-Rate Calculation
**What it checks:** quote rate and bind rate per carrier.

**Interpretation note — this is the rule Scenario 02 is built to
stress-test.** A percentage without its denominator is misleading, and
a percentage with a very small denominator (Vantage's 4 submissions)
must never be presented with the same visual/rhetorical confidence as
one with a much larger base (Ironclad's 22), even though both are
"just math." Any report surfacing a hit-rate figure must show the
underlying volume alongside it and should apply a low-volume annotation
below a configurable threshold (validate the specific threshold with
the design partner during discovery — the sample dataset uses 4 as an
illustrative low-volume case, not a proposed production cutoff).

### PR-03 — Time-to-Placement Calculation
**What it does:** measures elapsed time from submission to bind, per
carrier and per class.

**Interpretation note:** exclude periods where the delay is
attributable to the retail agent or insured (e.g., time spent waiting
on missing documents, per Package Assembly's BLOCKED status) from a
"carrier speed" framing specifically — conflating broker/agent-side
delay with carrier-side turnaround time would misattribute the cause of
slow placements and could unfairly make a carrier look slower than they
actually are.

### PR-04 — Revenue Attribution
**What it does:** attributes commission/revenue to carrier
relationships and, where meaningful, to individual brokers.

**Interpretation note:** no scenario in the sample dataset specifically
exercises this rule — flag as needing its own validation pass during
discovery once the design partner's actual commission structure and
revenue-recognition timing are understood, since these details are
brokerage-specific and shouldn't be assumed from general reasoning.

### PR-05 — Remarketing Value Realized
**What it checks:** what value did Renewal Remarketing's activity
actually produce over a reporting period?

**Interpretation note — this is the second rule Scenario 04 is built to
stress-test, and it directly extends a principle from the Renewal
Remarketing PRD itself.** That PRD's RR-04 interpretation guide
established that a FULL_REMARKET decision confirming the incumbent is
still the best option is a legitimate, valuable outcome, not a wasted
effort — this reporting rule must preserve that framing rather than
collapsing every remarket outcome into a single "$ saved" line that
would make a $0-savings confirmation look identical to a remarket that
simply failed to find anything. Report savings identified and
confirmation-value outcomes as distinct categories, not one merged
metric.

### PR-06 — Data Completeness Handling
**What it checks:** is the underlying data for a given report period
actually complete, and if not, is that gap explicitly surfaced?

**Interpretation note — this is the most important rule in this PRD,
and Scenario 03 exists entirely to test it.** When a logging gap exists
(a system migration, a workflow outage, an integration failure), the
report must flag the affected stage/period explicitly and must NEVER
interpolate, estimate, or silently omit the gap to produce a
cleaner-looking chart. This is the direct throughline back to the very
first critique in this entire project — the original landing page's
fabricated dashboard statistics — now applied to a legitimate internal
reporting context where the same discipline matters just as much,
arguably more, since real business decisions get made from these
numbers.

---

## Summary

| Scenario | Rules tested | Key check |
|---|---|---|
| 01 | PR-01, PR-06 (complete case) | Clean baseline funnel |
| 02 | PR-02 | Low-volume figures annotated, not ranked at face value |
| 03 | PR-06 | Data gap explicitly flagged, never smoothed over |
| 04 | PR-05 | Confirmation value distinguished from savings-only framing |
