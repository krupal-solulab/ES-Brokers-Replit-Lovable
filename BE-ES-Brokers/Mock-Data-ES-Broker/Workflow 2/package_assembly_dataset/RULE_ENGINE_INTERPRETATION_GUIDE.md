# Rule Engine Interpretation Guide — Submission Package Assembly

**Purpose:** same role as the Market Matching interpretation guide —
explains how to apply each rule correctly, including the specific
mistakes that are easy to make even with the rule definitions in hand.

---

## The core distinction in this workflow: assembly vs. fabrication

Every prior Coverline workflow had a grounding requirement ("never claim
something not in a source document"). This workflow pushes that
requirement into new territory, because its entire job is to **produce
documents**, not just recommendations — which creates real temptation to
fill gaps plausibly rather than flag them. The rules below exist
specifically to hold that line.

---

## Rule-by-rule interpretation

### PA-01 — Document inclusion per carrier requirements
**What it checks:** does the assembled package include every document
type on the target carrier's `required_documents` list, sourced from
already-extracted submission data?

**Interpretation note:** this rule operates **per carrier**, not per
submission. Scenario 03 exists specifically to test this — the same
underlying submission produces two different inclusion checklists
because Ironclad and Meridian have different requirements. Do not
compute one "package completeness" state for a submission and reuse it
across every carrier the broker selects; recompute independently for
each.

### PA-02 — Supplemental form auto-fill eligibility
**What it checks:** for carrier-specific supplemental forms/
questionnaires, which fields can be auto-populated from already-
extracted data, and which must be left for manual completion?

**Interpretation note — this is the most consequential rule in the
whole workflow to get right.** The test: **auto-fill only if the field
has a direct, cited source in already-extracted data. Never auto-fill
by inferring, estimating, or computing a value from other fields, even
if that computation is trivial and even if a carrier's own form metadata
suggests the field is "auto-fillable."** Scenario 04 is built exactly to
catch this — unit count could plausibly be estimated from Total
Insurable Value and property class, and a carrier's supplemental-form
metadata might even list it as derivable, but the system must still
leave it for the broker to enter manually, because it's an inference,
not an extraction. The distinction is subtle but important: extraction
finds a fact already stated in a document; inference computes a new fact
that was never actually stated anywhere. Only the former is safe to
auto-fill on a form an underwriter will rely on.

### PA-03 — Missing-item handling and package status
**What it checks:** given the results of PA-01, what overall status
should the package carry — `READY`, `READY_WITH_GAP`, or `BLOCKED`?

**Interpretation note:** these three states are not interchangeable
labels for "something's missing" — they have different implications for
what the broker should do next, and the system should assign them
consistently:
- `READY`: every required item present, no action needed before sending.
- `READY_WITH_GAP`: missing item(s) that are genuinely outside Coverline's
  ability to source (e.g., a third-party actuarial report, per Scenario
  01) — the broker can reasonably choose to send now and follow up
  separately, and the cover letter should proactively acknowledge the
  gap rather than let the carrier discover it.
- `BLOCKED`: missing item(s) that are either required and unsourced (a
  loss run with insufficient years) or require insured input Coverline
  cannot generate (an unanswered supplemental questionnaire) — the
  package should not be presented as ready to send, and the broker's
  next action is to go get the missing piece, not to decide whether to
  proceed anyway.

The distinction between `READY_WITH_GAP` and `BLOCKED` is a judgment
call that should be configurable per carrier/requirement combination
(similar in spirit to the `ceiling_type: hard | soft` configurability
established in the Market Matching rule engine) rather than a single
global threshold — some carriers may treat a documentation gap as a
minor administrative matter, others may treat the same gap as
disqualifying.

### PA-04 — Cover letter tone and emphasis selection
**What it checks:** how should the drafted cover letter frame the
submission, given both the account's specific risk profile and the
target carrier's stated appetite/risk tolerance?

**Interpretation note:** this rule directly extends the tone-framing
principles established in the MGA Broker Communication PRD (TN-01
through TN-17) into an *external, carrier-facing* context, which is a
higher-stakes register than internal broker-to-broker communication.
Two specific behaviors to get right:
- **Proactive disclosure over omission, always** — Scenario 05
  (Summit Roofing) is the hardest test of this: a cover letter to a
  higher-risk-tolerance carrier should lead with the loss history and
  frame *why this carrier specifically* is the right fit for this
  profile, not bury or minimize the claims. This isn't just an ethics
  position — a carrier that discovers a broker soft-pedaled loss history
  will trust that broker's future submissions less, which is a real
  relationship cost or the exact opposite of what a wholesale broker's
  business depends on.
- **Tone should reference the carrier's own stated appetite/notes where
  available**, not just swap the carrier's name into a fixed template —
  Scenario 05's cover letter explicitly references Ironclad's "known
  appetite for higher-severity roofing risk" (sourced from that
  carrier's profile `notes` field), which is what makes it read as
  genuinely tailored rather than templated.

### PA-05 — Format/version compliance
**What it checks:** does the assembled package use the document
formats/versions a specific carrier actually wants (e.g., ACORD 126 vs.
a carrier's proprietary supplemental form)?

**Interpretation note:** treat carrier form preferences as part of the
Carrier Appetite Profile schema (extend the schema from the Market
Matching PRD with a `preferred_form_versions` or `supplemental_form`
field, as modeled in Scenario 04's test data) rather than hardcoding
format logic into the assembly engine itself — this keeps format
preferences as maintainable data, consistent with how carrier appetite
itself is modeled, rather than as scattered special-case code.

### PA-06 — Diligent search documentation attachment
**What it checks:** if Market Matching's MM-07 check flagged that
diligent-search documentation is required and present, is it
automatically included in the assembled package?

**Interpretation note:** this should be a simple pass-through, not
recomputed — Market Matching already did the compliance check; Package
Assembly's job is just to make sure that result actually gets attached
to the outbound package rather than requiring the broker to remember to
do it separately (Scenario 05 tests this explicitly). If MM-07 flagged
documentation as `absent` rather than `present`, Package Assembly should
treat this as a `BLOCKED` condition per PA-03, not attempt to generate
the documentation itself (that's out of scope per the Market Matching
PRD's Section 2.2, and remains out of scope here).

### PA-07 — Duplicate/conflicting data reconciliation
**What it checks:** when a submission has been through both extraction
and Market Matching, and possibly manual broker edits in between, which
version of a given fact is authoritative for the final package?

**Interpretation note:** establish and document a clear precedence order
during implementation — e.g., broker-edited values (if the broker
corrected something in the Market Matching review step) should take
precedence over the original extraction, which takes precedence over any
carrier-side inferred defaults. This wasn't heavily exercised in the
sample dataset's scenarios (all six assume the extraction data is the
final word), but it's a real production scenario worth architecting for
now rather than retrofitting later, since brokers will edit data between
these two workflow steps in practice.

---

## Summary — expected outcomes per sample dataset scenario

| Scenario | Rules primarily tested | Expected status |
|---|---|---|
| 01 | PA-01, PA-03 (gap type distinction) | READY_WITH_GAP |
| 02 | PA-01, PA-02, PA-03 (blocking gaps) | BLOCKED |
| 03 | PA-01 (per-carrier independence), PA-04 (differentiated tone) | Two packages, different statuses/tones |
| 04 | PA-02 (auto-fill boundary) | READY, one field left manual |
| 05 | PA-04 (hardest tone test), PA-06 (diligent search pass-through) | READY |
| 06 | Control/baseline — all rules pass cleanly | READY |
