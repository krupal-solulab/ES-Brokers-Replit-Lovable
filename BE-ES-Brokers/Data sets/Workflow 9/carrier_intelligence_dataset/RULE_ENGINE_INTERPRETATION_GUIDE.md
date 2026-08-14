# Rule Engine Interpretation Guide — Carrier Appetite Intelligence Tracking

**Purpose:** same role as every prior guide, but read this one with an
unusual framing in mind: **the default, correct behavior for most of
these rules is to do nothing.** This workflow has been called out as
the vertical's highest scope-creep risk at every prior mention (Market
Matching's Section 2.2, Quote Comparison's QC-03, Renewal Remarketing's
RR-08 discussion) — these interpretation notes exist to keep it that
way, not to help it detect more.

---

### CI-01 — Signal Aggregation
**What it does:** collects declination-consistency signals already
logged (but not acted on) by Quote Comparison's QC-03 and Renewal
Remarketing's RR-08-adjacent history, plus any bind/endorsement
outcomes recorded elsewhere in this vertical, into a single per-carrier,
per-class view.

**Interpretation note:** this is pure aggregation of data already being
collected by other workflows — this rule should not introduce any new
data collection point, only assemble what already exists.

### CI-02 — Consistency Scoring
**What it checks:** how do observed outcomes compare to a carrier's
stated profile over time?

**Interpretation note — this is the rule most likely to be built
carelessly, and Scenario 03 exists to catch the specific mistake.** A
declined submission with an account-specific stated reason (severity too
high for *this* account) is fundamentally different evidence from a
declined submission with a class-level stated reason (carrier no longer
writes this class at all). Only the latter should count as a signal
toward a potential profile change. Scoring these identically will
produce constant false signals from entirely normal account-level
variance — which is exactly the noise this workflow must avoid to
justify existing at all.

### CI-03 — Staleness-Adjusted Confidence Update
**What it does:** when observed outcomes consistently confirm a
carrier's stated profile, refresh that profile's `appetite_confidence`
and `appetite_last_updated` metadata fields.

**Interpretation note — this is the ONE piece of this workflow allowed
to write back automatically, and the boundary must be exact.** Only
`appetite_confidence` and `appetite_last_updated` may be updated without
human approval. `class_codes_accepted`, `class_codes_excluded`,
`premium_band`, `severity_ceiling`, and every other substantive field on
the Carrier Appetite Profile schema (established in Market Matching)
remain permanently human-approval-gated, per CI-04 below. Do not let
this boundary drift during implementation — it is the single most
important architectural constraint in this PRD.

### CI-04 — Suggested Profile Change Generation
**What it does:** when CI-02 identifies a genuine, sufficiently-evidenced
pattern of inconsistency, generate a suggestion for human review.

**Interpretation note:** this is a suggestion queue, not an editing
capability. Scenario 02's expected output is explicit that the system
never auto-edits the accepted/excluded class lists — this is not framed
as a v1 limitation anywhere in this vertical's documentation, it is a
permanent structural constraint on this workflow, consistent with every
other "human always approves" boundary established since the very first
MGA PRD in this project. A future version of this workflow might make
suggestions faster or better-reasoned; it should never make them
self-executing.

### CI-05 — Suppression of Low-Signal Noise
**What it checks:** is there sufficient volume and consistency to
justify surfacing anything at all?

**Interpretation note — treat this as the default state, not an
exception path.** Scenario 01 (a single data point) and Scenario 03
(mixed signal with a non-class-level explanation) both test that the
system correctly produces *nothing*. Given how few outcomes any single
carrier/class combination will accumulate in a reasonable time window,
the overwhelming majority of this workflow's evaluations should end in
suppression. If a build produces frequent suggestions during testing,
that's a signal the suppression thresholds are miscalibrated, not that
the system is working well.

---

## Summary

| Scenario | Rules tested | Outcome |
|---|---|---|
| 01 | CI-05 (single data point) | SUPPRESSED |
| 02 | CI-02 (genuine pattern), CI-04 (human-reviewed suggestion) | SUGGESTION GENERATED |
| 03 | CI-02 (account-specific vs. class-level distinction), CI-05 | SUPPRESSED |
| 04 | CI-02 (consistent confirmation), CI-03 (metadata-only auto-update) | METADATA REFRESH ONLY |
