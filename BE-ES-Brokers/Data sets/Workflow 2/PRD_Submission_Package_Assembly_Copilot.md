# PRD: Submission Package Assembly Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Draft for engineering scoping
**Owner:** [Product]
**Last updated:** 2026-07-16
**Depends on:** Submission Market Matching Copilot (v1) — this workflow consumes a broker's carrier selection directly from that workflow's output and does not re-run extraction or matching logic.

---

## 1. Problem Statement

Once a wholesale broker selects which carrier(s) to approach for a submission, they still have to manually assemble the actual package: the right documents, in the right format, matching that specific carrier's stated requirements — which differ carrier to carrier — plus a cover letter/submission narrative that makes the case for why this risk fits this carrier. Wholesale brokers are often at the mercy of whatever data the retail agent passes along, and those submissions frequently arrive with gaps, missing details, or incomplete financials, which forces brokers into a manual, tedious process of chasing down missing information and patching holes themselves before a package can even go out the door. This work is repetitive per carrier (the same submission needs a different package for each carrier approached) and error-prone in a specific, costly way: sending an incomplete or mismatched package to a carrier wastes that carrier relationship's attention and damages the broker's credibility with that market.

**Goal of v1:** Given a submission and the carrier(s) a broker has selected from Market Matching, automatically assemble a carrier-specific package — checking document completeness against that carrier's actual requirements, auto-filling supplemental form fields only where genuinely extractable (never inferred), and drafting a tailored cover letter — for broker review before sending.

**Explicitly not the goal of v1:** Automatically sending anything to a carrier, sourcing missing documents from the insured, or generating diligent-search documentation from scratch (only attaching it if Market Matching already confirmed it exists — see Section 2.2).

---

## 2. Scope of v1

### 2.1 In scope
- Consuming Market Matching's output directly (carrier selection, per-carrier missing-info, diligent-search status) — no re-extraction, no re-matching
- Per-carrier document completeness checking against that carrier's `required_documents` and `min_loss_run_years`
- Three-state package status: `READY`, `READY_WITH_GAP`, `BLOCKED` (Section 6, PA-03)
- Supplemental form auto-fill, strictly bounded to directly-extracted fields only (Section 6, PA-02)
- Carrier-tailored cover letter drafting, grounded and citation-enforced
- Simultaneous multi-carrier package generation from one submission, correctly differentiated per carrier (Section 6, PA-01)
- Diligent-search documentation pass-through/attachment (not generation) where Market Matching already confirmed it's required and present
- Human reviews and manually sends every package — no automated carrier submission

### 2.2 Explicitly out of scope for v1
- Automated submission to carriers via portal, email, or API — this workflow ends at a broker-reviewed, ready-to-send package, same boundary as every other Coverline workflow
- Sourcing missing documents from the insured or retail agent directly (that's a broker action, potentially a future extension of the Retail Agent Communication Copilot, not this workflow)
- Generating diligent-search documentation from scratch — v1 only attaches it if Market Matching's MM-07 check already found it present; if absent, this workflow surfaces that as a blocking condition, it does not create the documentation
- Inferred/computed field auto-fill of any kind (Section 6, PA-02) — this is a permanent boundary for this workflow, not a v1 limitation to relax later, given the reasoning in the Rule Engine Interpretation Guide
- Package delivery/transmission tracking (confirming a carrier received and opened a package) — out of scope for v1

### 2.3 Success criteria (must hit before expanding scope)
- **Zero false-ready packages:** 0% of packages marked `READY` in the pre-launch eval should actually be missing a required document — this is the equivalent of Market Matching's zero-false-positive-hard-match gate, and it's just as consequential here: a package presented as ready that isn't damages the exact carrier relationship this whole vertical depends on
- **Auto-fill precision:** 100% of auto-filled supplemental form fields in the pre-launch eval must trace to a direct extracted source — zero tolerance for inferred/computed auto-fill reaching a broker-facing draft, treated as a hard quality gate per PA-02
- **Cover letter usability rate:** ≥75% of drafted cover letters sent with no more than minor edits, measured via the same edit-distance tracking pattern established in the MGA Broker Communication PRD
- **Time saved per package:** reduce broker time spent assembling a carrier-ready package by ≥50% against baseline measured during discovery

---

## 3. Users & Personas

| Persona | Role in this workflow |
|---|---|
| **Wholesale Broker / Production Underwriter** (primary user) | Reviews assembled package(s), fills any remaining gaps, edits cover letter, sends manually |
| **Brokerage Principal / Managing Partner** (secondary, buyer) | Cares about submission quality/consistency across the team and placement speed |
| **Carrier Underwriter** (indirect, non-user, recipient) | Receives the assembled package — the actual quality bar for this workflow is whether this person experiences a complete, well-framed submission |

---

## 4. End-to-End Workflow

```
1. Broker selects one or more carriers from a Market Matching ranked
   shortlist (this is the trigger — see Market Matching PRD Section 4,
   step 7)
2. Package Assembly receives the selection, the underlying extracted
   submission data, and each selected carrier's profile (requirements,
   appetite notes, diligent-search status)
3. For EACH selected carrier independently:
   a. Run document completeness check (PA-01) against that carrier's
      specific requirements
   b. Attempt supplemental form auto-fill where a direct extracted
      source exists (PA-02); leave all other fields for manual entry
   c. Determine package status: READY / READY_WITH_GAP / BLOCKED (PA-03)
   d. Draft a cover letter tailored to this carrier's appetite/notes and
      this submission's specific risk profile (PA-04)
   e. Verify format/version compliance with this carrier's stated
      preferences (PA-05)
   f. Attach diligent-search documentation if Market Matching confirmed
      it's required and present (PA-06)
4. Present each carrier's package independently to the broker — even
   when multiple carriers were selected simultaneously, each package is
   reviewed and can be sent on its own timeline, not as a single bundled
   action
5. Broker reviews: fills any BLOCKED items where possible, edits cover
   letter as needed, confirms package contents
6. Broker manually compiles/sends via their own email or carrier portal
   — the system does not transmit anything automatically
7. System logs: package status at generation, broker edits, and
   eventual outcome if tracked (this feeds the same Feedback/Eval Store
   pattern established across every Coverline workflow, and — longer
   term — the same underlying data that would eventually inform the
   deferred Carrier Appetite Intelligence workflow)
```

**Design principle, consistent with every workflow so far:** this system
assembles and drafts; the broker sends. That boundary matters even more
here than in most other workflows, because the artifact this workflow
produces goes directly to an external party whose trust in the
brokerage's professionalism is the actual product being protected.

---

## 5. Functional Requirements

### 5.1 Input Consumption

- **FR-1:** System must consume Market Matching's output object directly (per that PRD's Section 7.2 schema) — specifically the broker's carrier selection, each carrier's profile/requirements, and the diligent-search result — without re-running extraction or matching.
- **FR-2:** System must handle both single-carrier and multi-carrier simultaneous selections, treating each carrier as an independent assembly pass (per FR-7).

### 5.2 Document Completeness Checking

- **FR-3:** For each selected carrier, check the submission's available extracted documents against that carrier's `required_documents` list and `min_loss_run_years` — reusing the extracted data already produced upstream, not re-extracting anything.
- **FR-4:** This check must be computed independently per carrier (per PA-01) — a document set complete for one carrier and incomplete for another must be reflected as such in each carrier's own package status, never averaged or applied uniformly across a multi-carrier selection.

### 5.3 Supplemental Form Auto-Fill

- **FR-5:** For carriers with a defined supplemental/proprietary form (per the extended Carrier Appetite Profile schema, Section 7.1), auto-fill only fields with a direct, cited source in already-extracted submission data.
- **FR-6:** Never auto-fill a field via inference, computation, or estimation from other fields, even when a carrier's own form metadata suggests the field is derivable — per PA-02, this is a hard, permanent constraint, not a v1 limitation. Fields that can't be directly sourced must be clearly flagged for manual broker entry, never silently left blank or guessed.
- **FR-7:** Every auto-filled field must carry a citation back to its source (submission document + field), consistent with the grounding requirement established across every Coverline workflow.

### 5.4 Package Status Determination

- **FR-8:** Compute one of three states per carrier package: `READY`, `READY_WITH_GAP`, or `BLOCKED`, per the definitions in Rule PA-03.
- **FR-9:** The `READY_WITH_GAP` vs. `BLOCKED` distinction must be configurable per carrier/requirement-type combination (not a single global rule) — some missing items are genuinely outside Coverline's or the broker's immediate ability to source (treat as gap-with-disclosure), others should hold the package back entirely (treat as blocking). This configuration should live alongside the Carrier Appetite Profile data, not as separate hardcoded logic.
- **FR-10:** A `BLOCKED` package must never be presented with the same one-click "ready to send" affordance as a `READY` or `READY_WITH_GAP` package in the review UI — this mirrors the compliance-gate UI pattern established for Non-Renewal Notices in the MGA Broker Communication PRD.

### 5.5 Cover Letter Drafting

- **FR-11:** Draft a cover letter per carrier package, grounded in the submission's extracted data and citation-enforced per the standard established across every prior workflow.
- **FR-12:** Cover letter tone/emphasis must reference the specific target carrier's appetite notes and risk tolerance where available in that carrier's profile (per PA-04) — never a generic template with only the carrier name swapped.
- **FR-13:** When a submission has negative or notable risk signals (claims history, severity trends), the cover letter must proactively frame and disclose them rather than omit or minimize them — per PA-04's proactive-disclosure principle, this is treated as a hard content requirement, not a style preference, given the relationship-damage risk of a carrier discovering an undisclosed issue after the fact.
- **FR-14:** When a `READY_WITH_GAP` status applies, the cover letter must proactively acknowledge the specific gap (per Scenario 01's pattern) rather than silently omitting mention of it and hoping the carrier doesn't ask.

### 5.6 Format & Compliance Handling

- **FR-15:** Package documents must conform to each carrier's stated format/version preferences (ACORD version, proprietary supplemental forms) per PA-05, sourced from the extended Carrier Appetite Profile schema (Section 7.1).
- **FR-16:** If Market Matching's diligent-search check (MM-07) found required documentation to be `present`, this workflow must automatically attach it to the outbound package (PA-06) — a simple pass-through, not a recomputation.
- **FR-17:** If diligent-search documentation was flagged `absent` or `required` but unconfirmed, this must produce a `BLOCKED` status per FR-8/PA-03 — this workflow does not attempt to generate the missing documentation itself, per Section 2.2's scope boundary.

### 5.7 Human Review Interface

- **FR-18:** Each carrier package (even within a multi-carrier simultaneous selection) is presented and reviewable independently — a broker should be able to send the Ironclad package today and hold the Meridian package pending a follow-up document, without one blocking the other.
- **FR-19:** Package view shows: status (READY / READY_WITH_GAP / BLOCKED), document checklist with source citations, auto-filled supplemental fields (clearly marked as auto-filled vs. manual-entry-required), and the drafted cover letter.
- **FR-20:** One-click actions: Approve & Compile / Edit / Mark as sent (manual log, since actual transmission isn't automated) — consistent with the review-and-log pattern established across every Coverline workflow.
- **FR-21:** All broker edits (to auto-filled fields, cover letter, or manual gap-filling) logged for the feedback loop, per FR-17 in the MGA Broker Communication PRD's established pattern.

### 5.8 Non-Functional Requirements

- **FR-22:** Processing time per package (single carrier): target < 5 minutes — this workflow does no new extraction, so it should be faster than Market Matching's own 10-minute target.
- **FR-23:** For multi-carrier simultaneous selections, packages should generate in parallel, not sequentially — a broker selecting 3 carriers shouldn't wait 3x as long as selecting 1.
- **FR-24:** Same data retention, encryption, and access-control requirements as every prior Coverline workflow — no new compliance surface introduced here beyond what Market Matching already established.

---

## 6. Rule Engine

**See the companion document, `RULE_ENGINE_INTERPRETATION_GUIDE.md`, for
full interpretation notes and worked examples against the sample
dataset.** Summary:

| Rule ID | Rule | Type |
|---|---|---|
| PA-01 | Document inclusion per carrier requirements | Computed independently per carrier |
| PA-02 | Supplemental form auto-fill eligibility | Hard boundary — direct extraction only, never inference |
| PA-03 | Missing-item handling and package status | Three-state, configurable gap-vs-block threshold per carrier/requirement |
| PA-04 | Cover letter tone and emphasis selection | Carrier-aware, proactive-disclosure-required |
| PA-05 | Format/version compliance | Sourced from extended Carrier Appetite Profile schema |
| PA-06 | Diligent search documentation attachment | Pass-through from Market Matching's MM-07, not recomputed |
| PA-07 | Duplicate/conflicting data reconciliation | Precedence order: broker edits > extraction > inferred defaults (latter never used per PA-02) |

**All thresholds and the gap-vs-block configuration are placeholders**,
consistent with every rules document in this project, and must be
validated with the design partner during discovery — particularly PA-03's
threshold, which likely varies meaningfully by carrier and should be set
in collaboration with brokers who have real experience with each
carrier's actual tolerance for incomplete submissions.

---

## 7. Data Schemas

### 7.1 Extended Carrier Appetite Profile Schema
(adds to the schema defined in the Market Matching PRD, Section 7.1)

```json
{
  "...": "all fields from Market Matching PRD Section 7.1, plus:",
  "supplemental_form": "string, null if none",
  "supplemental_fields_auto_fillable": ["list of field names — informational only; PA-02 still requires a direct source at generation time regardless of what's listed here"],
  "preferred_form_versions": {"ACORD_liability": "string, e.g. 'ACORD 126 (2024)'"},
  "gap_vs_block_thresholds": {
    "missing_document_type": "block | disclose",
    "loss_run_year_shortfall": "block | disclose",
    "supplemental_form_incomplete": "block | disclose"
  }
}
```

### 7.2 Package Output Schema

```json
{
  "package_id": "string",
  "submission_id": "string",
  "carrier_id": "string",
  "carrier_name": "string",
  "status": "READY | READY_WITH_GAP | BLOCKED",
  "document_checklist": [
    {"document_type": "string", "included": "boolean", "source": "string, citation to extraction record"}
  ],
  "supplemental_form_fields": [
    {"field_name": "string", "value": "string, null if not auto-filled", "auto_filled": "boolean", "source_citation": "string, null if manual"}
  ],
  "diligent_search_attached": "boolean",
  "cover_letter": {
    "body": "string",
    "citations": [{"claim": "string", "source": "string"}]
  },
  "blocking_items": [{"item": "string", "reason": "string"}],
  "gap_items_disclosed": [{"item": "string", "cover_letter_acknowledgment": "boolean"}],
  "status_log": [{"action": "generated | edited | approved | marked_sent", "timestamp": "datetime", "user": "string"}]
}
```

---

## 8. System Architecture (Level 2)

```
┌───────────────────────────┐
│ Market Matching Output         │  (existing, per Market Matching PRD
│ (carrier selection, per-       │   Section 7.2 schema — consumed
│  carrier missing-info,          │   directly, no re-computation)
│  diligent-search result)        │
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Per-Carrier Assembly Loop      │◄─────┤ Extended Carrier Appetite     │
│ (runs independently for each   │      │ Profile DB (adds supplemental │
│  selected carrier — FR-2/FR-4) │      │  form + format preference      │
└────────────┬─────────────────┘      │  fields, Section 7.1)          │
             │                          └───────────────────────────┘
             ▼
┌───────────────────────────┐
│ Document Completeness Check    │  (PA-01, reuses already-extracted
│                                 │   submission data, no new extraction)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Supplemental Auto-Fill Engine  │  (PA-02 — hard boundary enforcement,
│                                 │   direct-source-only)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Package Status Engine          │  (PA-03 — READY / READY_WITH_GAP /
│                                 │   BLOCKED)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Cover Letter Generation Layer  │  (PA-04, grounded, citation-enforced,
│ (carrier-aware, proactive-     │   extends MGA Broker Comm's tone-
│  disclosure-required)          │   framing patterns)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Format/Diligent-Search          │  (PA-05, PA-06 — pass-through and
│ Compliance Layer                │   format-conformance checks)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Broker Review Interface         │◄──── Per-carrier independent review,
│ (per-carrier independent view,  │       edits logged here (FR-18-21)
│  per FR-18)                     │
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Feedback/Eval Store             │  (shared pattern with every prior
│                                  │   Coverline workflow)
└───────────────────────────────┘
```

**Key architectural point:** this is the lightest-weight build in the
Wholesale/E&S vertical so far — no new extraction, no new external data
source beyond extending the Carrier Appetite Profile schema that Market
Matching already introduced. The real engineering care needed here is
less about raw build complexity and more about **holding the line on
PA-02's auto-fill boundary** and **getting PA-03's three-state logic
right per carrier** — both are conceptually simple rules that are easy
to implement sloppily under time pressure, which is exactly why the
Rule Engine Interpretation Guide exists as a companion document rather
than leaving these as one-line bullet points in the PRD.

---

## 9. Risks & Open Questions

| Risk | Mitigation / Owner |
|---|---|
| Auto-fill boundary (PA-02) is the single highest-consequence rule in this PRD — a subtle violation (auto-filling an inferred field) could go unnoticed in testing if eval data happens not to exercise it | Treat Scenario 04 in the sample dataset as a mandatory, non-skippable eval case before any launch — this is the one test case in this PRD that should function as a release gate, not just a quality check |
| Cover letter proactive-disclosure requirement (FR-13) creates real tension with a broker's instinct to present their submission in the best light — there may be organizational pushback if this feels like it's working against the broker's interest | Frame this explicitly during discovery and training as a *relationship-protection* feature, not a compliance constraint — the reasoning in the Rule Engine Interpretation Guide (undisclosed issues cost future trust) should be presented to brokers directly, not just embedded silently in the product |
| Extended Carrier Appetite Profile schema (supplemental forms, format preferences, gap-vs-block thresholds) adds meaningfully more data-maintenance burden on top of what Market Matching already required | This compounds the "carrier profile maintenance is real ongoing work" risk already flagged in the Market Matching PRD — worth revisiting that discovery-phase ownership conversation now that the scope of what's being maintained has grown |
| Multi-carrier simultaneous package generation (FR-23) assumes carriers can be processed independently and in parallel — confirm this holds if any carrier-specific logic turns out to have cross-carrier dependencies (e.g., a broker's diligent-search obligation might depend on which OTHER carriers have already been approached, not just the current one) | Flag this as a discovery question rather than assuming full independence — the sample dataset's Scenario 03 tests parallel differentiation but doesn't test a case where one carrier's package logic depends on another's, which may or may not be a real scenario worth covering |

---

## 10. Rollout Plan

1. **Discovery (1-2 weeks — lighter than Market Matching's, since it extends rather than replaces that workflow's data foundation):** extend the carrier panel's profiles with supplemental form details and format preferences, confirm gap-vs-block thresholds per carrier with real underwriters, confirm cover letter tone expectations directly with brokers given the proactive-disclosure risk flagged above.
2. **Build v0 (3-4 weeks):** Per-carrier assembly loop, document completeness check, auto-fill engine (with PA-02's boundary as a first-class design constraint, not an afterthought), package status engine, cover letter generation layer, per-carrier review UI.
3. **Shadow mode (2 weeks):** generate packages for real Market Matching outputs in parallel with brokers' normal manual assembly process; compare against what brokers actually sent.
4. **Live pilot (3-4 weeks):** system output enters the real review queue, Section 2.3 metrics tracked weekly, with the auto-fill precision gate treated as non-negotiable throughout.
5. **Go/no-go review:** against Section 2.3 criteria — only then consider Quote Comparison & Recommendation (the next workflow on the vertical roadmap) as the natural following build, since it picks up the placement process exactly where this workflow leaves off.

---

*This document defines v1 scope only. Automated carrier transmission, insured-facing document requests, and diligent-search documentation generation should be treated as new PRD scope — and the inference-based auto-fill boundary in particular should be treated as a permanent product decision requiring deliberate reconsideration, not a default to relax as the system's extraction quality improves over time.*
