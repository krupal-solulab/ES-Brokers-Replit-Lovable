# PRD: Diligent Search & Compliance Documentation Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Draft for engineering scoping
**Owner:** [Product]
**Last updated:** 2026-07-16
**Depends on:** Submission Market Matching (v1), whose MM-07 check first introduced diligent-search flagging as informational logging. This PRD upgrades that flag into full documentation generation — the capability explicitly deferred at every prior mention of MM-07 (Market Matching, Package Assembly's PA-06, Quote Comparison, Binder & Policy Issuance).

---

## 1. Problem Statement

Many states require wholesale brokers to document that admitted-market carriers were approached and declined before placing business in the surplus lines market — a requirement that exists to protect the E&S market's role as a market of last resort, not a first choice. Today, MM-07 (in Market Matching) only flags whether this requirement applies and whether documentation appears present — it doesn't generate the actual compliant record, verify evidence sufficiency, or handle the real complexity of multi-state risks and export-list exemptions. Brokers currently assemble this documentation manually, and the two failure modes are both costly: under-documentation (a real compliance gap discoverable in an audit) and over-claiming (an affidavit asserting declinations that aren't actually backed by written evidence).

**Goal of v1:** Determine per-state diligent-search requirements and export-list exemptions, verify that declination evidence meets the state's evidentiary bar (written, not verbal), and generate compliant documentation only when that bar is met — blocking generation and flagging specific gaps otherwise.

**Explicitly not the goal of v1:** Automatically soliciting declinations from admitted carriers, filing documentation with any regulatory body, or making a final legal judgment call on ambiguous state requirements without human/legal sign-off.

---

## 2. Scope of v1

### 2.1 In scope
- Per-state (not per-submission) requirement determination (DS-01)
- Export-list and exemption checking, explicitly logged as a distinct outcome from "no documentation" (DS-02)
- Declination evidence sufficiency checking with a strict written-evidence bar (DS-03)
- Document generation, gated entirely on evidence sufficiency (DS-04)
- Retention tracking per applicable state requirements (DS-05)
- Multi-state risk handling as an explicit per-state checklist, never a collapsed single verdict

### 2.2 Explicitly out of scope for v1
- Automatically contacting admitted carriers to solicit declinations — this remains a broker action
- Any legal judgment call on ambiguous or novel state requirement interpretation — routed to human/legal review, never resolved by the system alone
- Filing or submitting documentation to any state regulator — this workflow produces the record, it doesn't transmit it anywhere beyond the broker's own file
- Automated export-list determination for edge cases where eligibility depends on account-specific factors beyond class code (e.g., size-based export eligibility, per Scenario 04's Florida note) — flagged for human confirmation, not resolved automatically

### 2.3 Success criteria (must hit before expanding scope)
- **Zero non-compliant document generation:** 0% of generated affidavits in the pre-launch eval should assert evidence not actually on file — this is the highest-stakes gate in this entire vertical, given the legal/fraud exposure of a wrong result, and should be treated as more severe than any other zero-tolerance gate built so far
- **Zero conflated exemption/absence states:** 100% of exemption determinations must be explicitly and distinctly logged, never indistinguishable from a missing-documentation state
- **Multi-state completeness:** 100% of multi-state risks must present a per-state checklist with explicit incomplete/pending markers for any state not yet confirmed — never a single collapsed status

---

## 3. Users & Personas

| Persona | Role in this workflow |
|---|---|
| **Wholesale Broker** (primary user) | Gathers declination evidence, reviews determinations, requests legal input on ambiguous cases |
| **Brokerage Principal / Managing Partner** (secondary) | Cares about audit-readiness and E&O/regulatory exposure |
| **Brokerage Compliance/Legal function** (reviewer) | Must validate the state-requirement reference data during discovery and resolve ambiguous determinations |

---

## 4. End-to-End Workflow

```
1. A submission requiring diligent-search consideration is identified
   (triggered from Market Matching's MM-07 flag, now fully processed
   here rather than just logged)
2. For each state where coverage applies, determine requirement status
   (DS-01) and export-list/exemption eligibility (DS-02)
3. For states requiring documentation, check declination evidence
   sufficiency against the state's stated minimum, applying a strict
   written-evidence bar (DS-03)
4. If sufficient: generate the compliant document (DS-04), grounded
   only in verified evidence
5. If insufficient: block generation and flag exactly what's missing
6. Broker reviews the per-state checklist, gathers any missing evidence,
   escalates ambiguous determinations to compliance/legal
7. System retains the final record (or exemption determination) per the
   applicable state's retention requirement (DS-05)
```

---

## 5. Functional Requirements

- **FR-1:** Evaluate requirement status independently for every state in a submission's states-of-operation list, never assuming uniformity across states.
- **FR-2:** Log export-list/exemption determinations as an explicit, distinct status from "documentation absent" — this must be structurally unambiguous in the data model (see Section 7), not inferable only from a blank field.
- **FR-3:** Evidence sufficiency checking must reject verbal-only declinations as not meeting a written-evidence requirement, and must state exactly what additional evidence is needed when insufficient.
- **FR-4:** Document generation must be fully gated on FR-3's sufficiency check passing — no partial or best-effort document generation when evidence is incomplete.
- **FR-5:** Every fact in a generated document (carrier name, date, evidence type) must be grounded to a specific declination record — no invented or inferred entries, consistent with the grounding standard across every Coverline workflow, applied here at maximum strictness given the legal stakes.
- **FR-6:** Multi-state risks must produce a per-state checklist view, with any state lacking a confirmed determination explicitly marked pending — never defaulted to match already-confirmed states.
- **FR-7:** Ambiguous or account-specific exemption eligibility (e.g., size-dependent export eligibility) must be flagged for human/legal review, not resolved automatically.
- **FR-8:** Retention periods applied per DS-05 must be sourced from validated, state-specific legal reference data — this reference data is a required discovery input, not something to derive from general reasoning.

---

## 6. Rule Engine

**See the companion `RULE_ENGINE_INTERPRETATION_GUIDE.md` for full
interpretation notes.** Summary: DS-01 (per-state requirement), DS-02
(exemption, explicitly distinct from absence), DS-03 (strict written-
evidence sufficiency), DS-04 (grounded generation, fully gated on DS-03),
DS-05 (state-specific retention).

---

## 7. Data Schemas

```json
{
  "compliance_record_id": "string",
  "submission_id": "string",
  "named_insured": "string",
  "state_determinations": [
    {
      "state": "string",
      "requirement_status": "REQUIRED | EXEMPT | PENDING_DETERMINATION",
      "exemption_basis": "string, null unless EXEMPT — must be populated whenever status is EXEMPT",
      "declinations_required": "integer, null if exempt",
      "declinations_on_file": [{"carrier": "string", "date": "date", "written_evidence": "boolean"}],
      "sufficiency_status": "SUFFICIENT | INSUFFICIENT | NOT_APPLICABLE",
      "gap_detail": "string, null if sufficient",
      "document_generated": "boolean",
      "retention_period_years": "integer, null if not yet sourced"
    }
  ],
  "overall_status": "COMPLETE | PARTIAL | BLOCKED"
}
```

---

## 8. Risks & Open Questions

| Risk | Mitigation |
|---|---|
| State requirement and retention reference data requires real legal validation, not general research — this is the same caution flagged at MM-07's original introduction, now fully load-bearing | Mandatory legal/compliance discovery input before this workflow processes a single live submission; treat as a launch-blocking dependency, not a parallel workstream |
| Export-list eligibility can depend on account-specific factors (size, purchaser sophistication) beyond class code alone in some states | FR-7 routes these to human review — resist the temptation to build a more "complete" automated determination without expert validation of the actual rule logic per state |
| Generating a non-compliant document is a more severe failure mode here than a bad recommendation anywhere else in this vertical | Treat FR-4/FR-5 as the highest-priority release gate in this entire project — recommend a dedicated legal review of a sample of generated documents before go-live, beyond standard eval |

---

## 9. Rollout Plan

1. **Discovery (2-3 weeks, legal-heavy):** validate state requirement/export-list/retention reference data with the design partner's compliance function — this is likely the longest discovery phase of any workflow built so far, given the legal stakes.
2. **Build v0 (3 weeks):** per-state determination engine, evidence sufficiency checker, gated document generator, checklist UI.
3. **Shadow mode (2 weeks) with mandatory legal spot-check** of generated documents before any live use.
4. **Live pilot (3-4 weeks):** Section 2.3 gates tracked, zero-tolerance on non-compliant generation.

---

*This document defines v1 scope only. Automated carrier solicitation and regulatory filing integration should be treated as new PRD scope requiring fresh legal review.*
