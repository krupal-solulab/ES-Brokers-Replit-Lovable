# Rule Engine Interpretation Guide — Diligent Search & Compliance Documentation

**Purpose:** same role as every prior guide. This workflow has the
highest baseline legal stakes of anything built in this vertical —
every rule here produces or withholds a document that may be relied on
in a regulatory inquiry, so the interpretation notes below lean more on
"never do X" than on nuanced judgment calls.

---

### DS-01 — State Requirement Determination
**What it checks:** does the risk's state(s) of operation require
diligent search documentation for E&S placement at all?

**Interpretation note:** this must be evaluated **per state**, not once
per submission — Scenario 04 tests this directly. A multi-state risk
does not get a single yes/no; every state where coverage applies needs
its own determination, and an incomplete check (some states verified,
others not) must be presented as incomplete, never silently treated as
"probably fine because the checked states were fine."

### DS-02 — Export List / Exemption Check
**What it checks:** is the specific class code exempt from diligent
search in this state, whether via a general export list or an
exempt-commercial-purchaser type provision?

**Interpretation note — the most important distinction in this rule:**
an exemption and an absence of documentation produce the same visible
state (no affidavit on file) unless the system explicitly logs *why*.
Scenario 02 tests that an exemption is recorded as its own positive
determination — with the specific basis cited (export list, statute
reference) — not simply left blank. A blank field and an exemption
should never be visually or structurally indistinguishable in the
system's records.

### DS-03 — Declination Evidence Sufficiency
**What it checks:** does the number and quality of admitted-market
declinations on file meet the state's stated minimum?

**Interpretation note:** hold a strict bar on what counts as evidence.
Per Scenario 03, a verbal decline without written confirmation should
not count toward the requirement — the whole point of this
documentation is to withstand a regulatory audit, and a document
attesting to evidence that doesn't actually exist in written form is a
liability, not a convenience. When evidence is insufficient, the system
must state exactly what's missing (how many more declinations, or which
existing ones need to be upgraded from verbal to written) rather than a
generic "insufficient" flag.

### DS-04 — Document Generation Accuracy
**What it checks:** does the generated affidavit/document accurately
reflect only the evidence actually on file?

**Interpretation note:** this is the grounding requirement established
across every Coverline workflow, applied to its highest-stakes context
yet — never generate a document listing a declination, a date, or a
carrier name that isn't backed by an actual record. If DS-03 finds
insufficient evidence, DS-04 must not run at all for that submission;
document generation should be gated entirely on evidence sufficiency,
not attempted with gaps.

### DS-05 — Recordkeeping / Retention
**What it checks:** is the diligent search record (or exemption
determination) retained per the applicable state's record-retention
requirement?

**Interpretation note:** retention periods vary by state and are a pure
compliance/legal input, not something to infer from general reasoning —
this reference data needs the same expert legal validation flagged
throughout this vertical's compliance-adjacent rules (Market Matching's
MM-07 discovery note applies equally here).

---

## Summary

| Scenario | Rules tested | Outcome |
|---|---|---|
| 01 | DS-01, DS-02 (not exempt), DS-03 (sufficient), DS-04 | READY |
| 02 | DS-01, DS-02 (exemption, explicitly logged) | EXEMPT |
| 03 | DS-03 (insufficient/verbal-only evidence) | BLOCKED |
| 04 | DS-01/DS-02 applied per-state, incompleteness flagged | PARTIAL |
