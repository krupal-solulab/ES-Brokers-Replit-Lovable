# Rule Engine Interpretation Guide — Binder & Policy Issuance Coordination

**Purpose:** same role as every prior interpretation guide in this
project. This workflow introduces the most consequential trust question
yet in the Wholesale/E&S vertical, so read this guide carefully before
implementing — several of these rules are easy to get subtly wrong in a
way that looks correct in testing and only fails in production.

---

## The core principle underneath every rule in this workflow

Every prior workflow in this vertical checked Coverline's *own*
extracted or generated data for correctness. This workflow, for the
first time, has to check **an external party's output** — a carrier's
bind confirmation, a carrier's issued policy document — against what
was actually agreed. This is a fundamentally different trust posture:
**a document coming from a carrier is not automatically correct just
because it's the carrier's own official output.** Carriers make
processing errors, transcription mistakes, and occasionally bind
something slightly different from what was quoted without flagging the
change. Every reconciliation rule below (BI-03, BI-05) exists because of
this, and it's the single most important thing to get right in this
entire PRD.

---

## Rule-by-rule interpretation

### BI-01 — Bind order composition accuracy
**What it checks:** does the bind order sent to the carrier reflect
exactly the terms the broker selected from Quote Comparison — no drift,
no rounding, no summarization that loses precision?

**Interpretation note:** this is a straightforward grounding/fidelity
check, consistent with the grounding requirement established across
every Coverline workflow — the bind order is generated *from* the
broker's selection, not re-derived or re-summarized from the underlying
submission data, which reduces the risk of introducing drift at this
step. Treat the broker's selected quote (from Quote Comparison's output)
as the single source of truth for what the bind order should say.

### BI-02 — Pre-bind subjectivity clearance and blocking logic
**What it checks:** have all subjectivities classified as `material` and
`lifecycle_stage: PRE_BIND` (inherited from Quote Comparison's QC-02
classification) actually been cleared before the bind order is eligible
to be sent to the carrier?

**Interpretation note:** this directly extends the BLOCKED status
concept from Package Assembly (PA-03) and the material-subjectivity
concept from Quote Comparison (QC-02) into this workflow's own gating
logic. Scenario 02 tests this explicitly — a bind order should never be
presented as ready-to-send while a material pre-bind subjectivity
(the loss control inspection) remains open, regardless of how close the
effective date is or how much broker pressure exists to move faster.
**Do not re-classify subjectivities from scratch in this workflow** —
inherit the routine/material and pre-bind/post-bind classification
directly from Quote Comparison's QC-02 output rather than re-running
that judgment independently, which risks producing an inconsistent
answer between the two workflows for the same underlying condition.

### BI-03 — Carrier bind confirmation reconciliation
**What it checks:** does the carrier's bind confirmation match the
originally requested bind terms on every material field — premium,
limits, deductible, effective date?

**Interpretation note — this is the first of the two most important
rules in this PRD.** Scenario 03 is built specifically to test the
temptation to treat a binder number as proof of a clean, correct bind.
**A binder number confirms that *something* was bound — it does not
confirm that what was bound matches what was requested.** When a
discrepancy is found, the correct system behavior is to surface *both*
values (requested vs. confirmed) side by side and require explicit
broker acknowledgment of which is correct — never silently prefer one
over the other. A carrier's confirmed terms might reflect a legitimate
last-minute verbal change the broker forgot to log, or it might be a
processing error; the system cannot know which without a human
resolving it, and guessing wrong in either direction has real
consequences (either overriding a broker's correct request with a
carrier's mistake, or flagging a legitimate change as an error and
creating unnecessary friction).

### BI-04 — Policy issuance timeline monitoring
**What it checks:** has the carrier's own stated issuance timeline (from
the bind confirmation) been exceeded without policy documents actually
arriving?

**Interpretation note:** this needs to run as an ongoing, scheduled
check per bound account, not a one-time check at bind time — consistent
architecturally with the Quote Validity Monitor from the Quote
Comparison PRD and the Renewal Trigger Service pattern from the MGA
Renewal Management PRD. Scenario 05 tests that this generates a
proactive alert once the carrier's own stated deadline (not an arbitrary
Coverline-imposed one) is exceeded — using the carrier's own timeline as
the threshold is important, since it means the alert is grounded in a
real commitment the carrier made, not a generic guess.

### BI-05 — Issued policy vs. bound terms reconciliation
**What it checks:** once the final policy document arrives, does it
match the terms that were actually confirmed at bind?

**Interpretation note — this is the second, and arguably the single
most valuable, rule in this entire PRD.** Scenario 06 is built around a
real, known failure mode in the insurance industry: a policy document
that quietly doesn't match what was bound and communicated to the
retail agent and, ultimately, the insured. In Scenario 06's case, a
doubled wind/hail deductible ($100,000 issued vs. $50,000 bound) means
the insured would unknowingly be carrying twice the retained risk they
believe they have. **This check must run field-by-field against the
confirmed bind record (not the original quote, and not the original
submission request — the bind confirmation is the correct baseline,
since that's what was actually agreed after any BI-03 discrepancies
were already resolved).** Any material mismatch must block the
downstream "policy delivered, transaction complete" communication to
the retail agent (per BI-06) until resolved — this is not a check that
can be soft-failed or downgraded to a warning; treat it with the same
seriousness as the zero-false-positive gates established in Market
Matching and Package Assembly.

### BI-06 — Downstream trigger gating
**What it checks:** should this workflow's output fire the Retail Agent
Communication Copilot's Placement Confirmation (or a new Policy
Documents Delivered trigger) automatically?

**Interpretation note:** only a genuinely clean, verified state should
fire these downstream communications:
- Placement Confirmation fires only after BI-03 finds no discrepancy
  (or after a discrepancy has been explicitly resolved by the broker).
- A Policy Documents Delivered communication (a new trigger type this
  workflow introduces to the Retail Agent Communication Copilot, not
  yet specified in that PRD — flag as a follow-up scope item) should
  fire only after BI-05 finds no material discrepancy.

Scenarios 03 and 06 both test that these triggers are correctly
suppressed, not just that the discrepancies themselves are detected —
detecting a problem but still notifying the retail agent that
everything is fine would be worse than not detecting the problem at
all, since it actively propagates the error downstream with an implied
Coverline endorsement of its correctness.

### BI-07 — Post-bind ongoing obligation tracking
**What it checks:** for subjectivities classified as
`lifecycle_stage: POST_BIND_ONGOING` (a report due within a set number
of days after binding, a required follow-up action), does the system
track them as open tasks with reminders, distinct from pre-bind blockers?

**Interpretation note:** Scenario 04 tests the direct contrast against
Scenario 02 — the same *type* of requirement (a loss control
report/inspection) is handled completely differently depending on its
lifecycle stage. A post-bind ongoing obligation must NOT block the bind
itself (the bind already happened, coverage is in force), but it also
must not be silently dropped once the bind is confirmed — it needs to
persist as a tracked task with its own deadline and reminder cadence,
independent of whether the bind order or the policy issuance check are
otherwise complete. Losing track of a post-bind obligation (e.g., a
carrier-required loss control report) can jeopardize coverage just as
much as missing a pre-bind subjectivity, just on a delayed timeline —
treat this as equally important to get right, not a lesser concern
just because it doesn't block anything immediately.

---

## Summary — expected outcomes per sample dataset scenario

| Scenario | Rules primarily tested | Outcome |
|---|---|---|
| 01 | BI-01, BI-02 (nothing blocking), BI-03 (clean match), BI-04 (monitoring initiated) | Clean bind, Placement Confirmation fires |
| 02 | BI-02 (blocking logic) | BLOCKED — bind order not sent |
| 03 | BI-03 (confirmation discrepancy), BI-06 (trigger suppression) | Discrepancy flagged, Placement Confirmation held |
| 04 | BI-02 (correctly not blocking) vs. BI-07 (ongoing tracking) | Clean bind + tracked post-bind task |
| 05 | BI-04 (overdue monitoring) | Proactive overdue alert |
| 06 | BI-05 (policy reconciliation), BI-06 (trigger suppression) | Material discrepancy flagged, downstream trigger held |
