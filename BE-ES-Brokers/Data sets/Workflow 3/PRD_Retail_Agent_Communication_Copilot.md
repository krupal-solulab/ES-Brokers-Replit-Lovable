# PRD: Retail Agent Communication Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Draft for engineering scoping
**Owner:** [Product]
**Last updated:** 2026-07-16
**Depends on:** Submission Market Matching Copilot (v1) and Submission Package Assembly Copilot (v1) — this workflow drafts communication from data those two workflows already produce, and does not extract or analyze any new documents, following the same architectural pattern as the MGA Broker Communication Copilot.

---

## 1. Problem Statement

Every step of the placement process — a submission acknowledgment, a missing-info request, a "we couldn't find a market" notice, a quote summary, a bound confirmation — eventually has to become an email to the retail agent who originated the business. Wholesale brokers already have this data in structured form once Market Matching or Package Assembly has run, but today they write these updates individually, by hand, every time. This is the same underlying problem the MGA Broker Communication Copilot solves, applied to a different relationship (wholesaler-to-retail-agent instead of MGA-to-broker) with some genuinely different stakes: wholesale placements can end in a real "no market found" outcome that has no MGA-side equivalent, and successful quotes frequently carry pricing that needs active justification rather than simply being presented as a number.

**Goal of v1:** Draft retail-agent-facing communications directly from the structured output of Market Matching and Package Assembly, correctly calibrated in tone to the situation — routine status update, missing-info request, sensitive no-market notice, or price-justified quote summary — for broker review and manual send.

**Explicitly not the goal of v1:** Auto-sending any communication, negotiating with retail agents, handling their replies, or making the carrier-name-disclosure decision described in Section 6 without explicit compliance sign-off.

---

## 2. Scope of v1

### 2.1 In scope
- Six communication types, each mapped to an existing Market Matching / Package Assembly output or a defined trigger condition (Section 5.2)
- Draft generation only — every communication requires broker review and manual send, no exceptions
- Tone calibration based on communication type, retail agent relationship context, and — for two specific types — carrier acceptance-window data and pricing-context data
- Same wholesale brokerage, same line of business as Market Matching/Package Assembly v1 — no new integration surface

### 2.2 Explicitly out of scope for v1
- Auto-sending any communication under any circumstances — same permanent boundary established in the MGA Broker Communication PRD, and if anything more consequential here given the No Market Found communication type's compliance sensitivity
- Handling retail agent replies or multi-turn conversation
- The Quote Comparison workflow itself (comparing multiple carrier responses) — v1's Quote/Terms Summary and Placement Confirmation triggers assume a broker has already manually identified the relevant quote/bound terms; automating quote comparison itself is the next workflow on the roadmap, not this one
- SMS/text or phone-call scripting — email only
- Determining whether carrier-specific declination detail may be disclosed to retail agents — this is a compliance decision to be made during discovery (Section 6, RA-TN-06), not a product default this PRD resolves unilaterally

### 2.3 Success criteria (must hit before expanding scope)
- **Draft usability rate:** ≥80% of drafts sent with no edits or only minor edits, mirroring the MGA Broker Communication PRD's bar
- **Tone appropriateness:** 100% of drafts for the two highest-sensitivity categories (No Market Found, Quote/Terms Summary with pricing justification) pass manual tone review before any live use — hard launch gate, not a target to improve toward
- **Zero unauthorized carrier-name disclosure:** 0 instances of a No Market Found draft naming a specific declining carrier before the compliance question in Section 6 is formally resolved — this is a distinct, additional hard gate beyond the general tone-appropriateness one, given the real commercial-sensitivity risk involved
- **Time saved per communication:** reduce average time-to-draft by ≥60% against baseline, consistent with the efficiency bar set by the MGA equivalent given this workflow's similarly low engineering complexity

---

## 3. Users & Personas

| Persona | Role in this workflow |
|---|---|
| **Wholesale Broker / Production Underwriter** (primary user) | Reviews and edits drafts, sends manually |
| **Brokerage Principal / Managing Partner** (secondary) | May review sensitive drafts (No Market Found, high-priced quotes) before they go out, especially for newer or strategic retail agent relationships |
| **Retail Agent** (indirect, non-user, recipient) | Receives the communication — the quality bar for this workflow is whether the agent has a good experience and can confidently relay information to their own client |
| **Brokerage Compliance/Legal function** (reviewer, discovery input) | Must resolve the carrier-name-disclosure question (Section 6) before No Market Found communications go live |

---

## 4. End-to-End Workflow

```
1. Market Matching or Package Assembly produces an output object
   (carrier selection, package status, zero-match result), OR a broker
   manually logs a quote/bind outcome (since Quote Comparison isn't
   built yet in v1 — see Section 2.2)
2. Retail Agent Communication Copilot receives this as a trigger
3. System classifies which communication type applies (Section 5.2)
4. System retrieves relevant context: retail agent relationship data
   (tenure, volume), carrier-specific data where relevant (acceptance
   window for follow-ups, pricing-context for quote summaries),
   communication history for this submission thread
5. System selects the appropriate tone/framing pattern (Section 6 /
   companion Tone & Framing Rules Guide)
6. System drafts the communication, grounded in the specific facts from
   the triggering output object — never fabricates specifics
7. For No Market Found drafts specifically: system defaults to
   aggregate-level framing (no carrier names) per RA-TN-06, pending
   compliance resolution
8. Draft is placed in broker's review queue, attached to the relevant
   submission record
9. Broker reviews, edits as needed, sends manually
10. System logs: draft generated, edit distance, send timestamp — same
    feedback-loop pattern as every prior Coverline workflow
11. For No-Response Follow-up specifically: system monitors for a reply
    within the relevant carrier's acceptance window (not a fixed
    default) and generates at most one follow-up if none received
```

**Design principle, consistent with the MGA Broker Communication PRD:**
this workflow has minimal autonomy by design, and that's permanent, not
a v1 constraint to relax. Retail agent relationships are the wholesale
brokerage's distribution channel in exactly the way broker relationships
are an MGA's — the downside of a wrongly-timed or wrongly-toned
communication (a damaged agent relationship) outweighs the modest time
savings of removing the human review step, and that asymmetry holds
regardless of how good draft quality becomes over time.

---

## 5. Functional Requirements

### 5.1 Trigger Ingestion

- **FR-1:** System must consume Market Matching output objects (per that PRD's Section 7.2 schema) and Package Assembly output objects (per that PRD's Section 7.2 schema) as structured input — no new document parsing required.
- **FR-2:** System must support a manually-logged trigger path for Quote/Terms Summary and Placement Confirmation in v1, since the Quote Comparison workflow that would normally produce this data automatically isn't built yet (per Section 2.2) — a broker should be able to manually enter quoted/bound terms to trigger a draft, rather than waiting for that future workflow.
- **FR-3:** System must retrieve retail agent relationship context (tenure, volume tier) where available, defaulting to neutral tone if unavailable — same fallback pattern as the MGA equivalent's FR-4.

### 5.2 Communication Type Mapping

| Trigger type | Source | Triggered by | Tone category |
|---|---|---|---|
| Submission Acknowledgment | Market Matching / Package Assembly | Submission successfully processed and at least one carrier approached | Routine, informative |
| Missing Info Request (carrier-specific) | Package Assembly `BLOCKED` or `READY_WITH_GAP` | Blocking or disclosable gap present | Routine, precisely scoped to the relevant carrier |
| No Market Found | Market Matching `zero_match_result: true` | No carrier survives hard exclusion | **Highest sensitivity** — see Section 6, RA-TN-06/07 |
| Quote/Terms Summary | Manual broker input (v1) / future Quote Comparison workflow | Carrier response received | **Sensitive when pricing needs justification** — see Section 6, RA-TN-08/09/10 |
| Placement Confirmation | Manual broker input (v1) / future workflow | Carrier binds | Positive, efficient |
| No-Response Follow-up | Time elapsed since prior communication, measured against carrier's `acceptance_window_days` | No reply within a carrier-specific threshold | Gentle, calibrated to real urgency per RA-TN-05 |

- **FR-4:** A single submission may produce multiple simultaneous communications if multiple carriers are being pursued (e.g., one carrier's package went in clean while another's is blocked) — these should be combined into one coherent draft per the retail agent's need to understand the whole picture, not fragmented into separate emails about the same submission, mirroring FR-5 from the MGA Broker Communication PRD.
- **FR-5:** System must not generate a duplicate draft for an unresolved existing trigger, mirroring FR-6 from the MGA equivalent.

### 5.3 Draft Generation

- **FR-6:** Every factual claim must be grounded in the triggering output object's data — no fabricated specifics, reusing the standard grounding constraint from every prior Coverline workflow.
- **FR-7:** Drafts must include a clear, specific next step, per the same requirement as the MGA equivalent.
- **FR-8:** No Market Found drafts must default to aggregate-level panel framing (no specific carrier names) per RA-TN-06, and must carry a non-dismissable compliance-review indicator in the UI until the carrier-name-disclosure question is formally resolved with the design partner — mirroring the compliance-gate pattern established for MGA Non-Renewal Notices.
- **FR-9:** Quote/Terms Summary drafts must connect any pricing context (where available in the trigger data) to the specific underlying factor driving it, per RA-TN-08 — never present an elevated price without grounded justification.
- **FR-10:** System must generate an appropriate subject line, following the existing submission thread's subject line for reply-in-thread communications (missing info follow-ups, no-response follow-ups) rather than breaking the thread.

### 5.4 No-Response Follow-up Logic

- **FR-11:** Follow-up threshold must be calculated against the relevant carrier's `acceptance_window_days` (from the Carrier Appetite Profile schema), not a fixed default — per RA-TN-05, this is a meaningful departure from the MGA equivalent's fixed-threshold approach, since wholesale acceptance windows vary considerably by carrier and are often longer than MGA renewal deadlines.
- **FR-12:** At most one follow-up per original communication in v1, consistent with the MGA equivalent's anti-nagging constraint (FR-13 in that PRD).
- **FR-13:** Follow-up must reference the actual remaining time in the relevant acceptance window where known, giving the agent concrete, honest urgency context rather than a generic prompt.

### 5.5 Human Review Interface

- **FR-14:** Drafts appear in a review queue attached to the relevant submission record, consistent with the UI pattern established across every Coverline workflow.
- **FR-15:** One-click actions: Approve & Send (where a send connector exists) / Edit then Send / Discard — reusing the MGA equivalent's interaction pattern.
- **FR-16:** No Market Found drafts require the additional compliance-review step before standard send actions become available (per FR-8).
- **FR-17:** Edited drafts diffed and logged for the feedback loop, reusing the MGA equivalent's edit-distance tracking (FR-17 in that PRD).

### 5.6 Non-Functional Requirements

- **FR-18:** Draft generation latency: target < 2 minutes, consistent with the MGA equivalent's target given the similarly low computational complexity of this workflow.
- **FR-19:** Same data retention, encryption, and access-control requirements as every prior Coverline workflow.
- **FR-20:** System must never auto-send under any failure mode — same hard architectural guarantee (no code path calls a send action without a preceding explicit user click) established as FR-21 in the MGA Broker Communication PRD, extended here without modification.

---

## 6. Tone & Framing Rules

**See the companion document, `TONE_FRAMING_RULES_GUIDE.md`, for the full
rule set, including which rules carry over unchanged from the MGA Broker
Communication PRD and which are genuinely new to this vertical.**
Summary of what's new or meaningfully different:

| Rule ID | Rule | What's different from the MGA version |
|---|---|---|
| RA-TN-05 | Urgency calibration against real carrier acceptance windows | MGA version used fixed effective-date deadlines; this version requires per-carrier variable thresholds |
| RA-TN-06 | No carrier-specific declination disclosure without compliance clearance | Entirely new — no MGA-side equivalent, requires a discovery-phase compliance decision |
| RA-TN-07 | Separate market-access constraint from account quality (No Market Found) | Extends MGA's Non-Renewal framing (TN-08) to a new-business-declination context |
| RA-TN-08 | Connect quote pricing to specific grounded cause | Entirely new — MGA Quote Summary never needed pricing justification |
| RA-TN-09 | Honest reframing relative to realistic alternative (only when true) | Entirely new — depends on this vertical's real possibility of a zero-match outcome |
| RA-TN-10 | Relationship-tenure-aware explanatory depth on pricing communications | Extends MGA's general tenure-awareness (TN-04/07) to a pricing-specific application |

**RA-TN-06 in particular should be treated as a launch-blocking discovery
item**, not a rule to encode from assumption — confirm with the design
partner's compliance/legal function whether and how carrier-level
appetite/declination information may be shared with retail agents before
this communication type goes live in any form beyond the conservative
aggregate-framing default.

---

## 7. Data Schemas

### 7.1 Draft Communication Output Schema

```json
{
  "draft_id": "string",
  "trigger_type": "SUBMISSION_ACKNOWLEDGMENT | MISSING_INFO_REQUEST | NO_MARKET_FOUND | QUOTE_TERMS_SUMMARY | PLACEMENT_CONFIRMATION | NO_RESPONSE_FOLLOWUP",
  "source_workflow": "Market Matching | Package Assembly | Manual Input",
  "source_record_id": "string",
  "named_insured": "string",
  "retail_agent_name": "string",
  "retail_agency": "string",
  "subject_line": "string",
  "body": "string",
  "requires_compliance_review": "boolean",
  "carrier_names_disclosed": "boolean",
  "grounding_citations": [{"claim": "string", "source_field": "string"}],
  "status": "DRAFT | UNDER_COMPLIANCE_REVIEW | APPROVED | EDITED | SENT | DISCARDED",
  "edit_distance_from_original": "float, null until sent or discarded",
  "generated_timestamp": "datetime",
  "sent_timestamp": "datetime, null until sent"
}
```

### 7.2 Retail Agent Relationship Context Schema

```json
{
  "retail_agent_name": "string",
  "retail_agency": "string",
  "relationship_tenure_years": "float, null if unavailable",
  "volume_tier": "low | moderate | high, null if unavailable",
  "communication_history_for_this_thread": [
    {"communication_type": "string", "sent_timestamp": "datetime", "reply_received": "boolean"}
  ]
}
```

---

## 8. System Architecture (Level 2)

```
┌───────────────────────────┐  ┌───────────────────────────┐  ┌──────────────────┐
│ Market Matching Output       │  │ Package Assembly Output      │  │ Manual Broker Input │
│ (existing schema)             │  │ (existing schema)             │  │ (v1 fallback for      │
└────────────┬─────────────────┘  └────────────┬─────────────────┘  │  quote/bind triggers) │
             │                                   │                    └──────────┬──────────┘
             └──────────────┬────────────────────┴──────────────────────────────┘
                             ▼
              ┌───────────────────────────┐
              │ Trigger Classification        │  (Section 5.2 mapping)
              └────────────┬─────────────────┘
                            ▼
              ┌───────────────────────────┐
              │ Retail Agent Context           │  (CRM query or neutral
              │ Retrieval                      │   default, per FR-3)
              └────────────┬─────────────────┘
                            ▼
              ┌───────────────────────────┐
              │ Tone/Framing Rule Selection    │  (deterministic routing —
              │ (RA-TN rules, Section 6)       │   which ruleset applies is
              │                                 │   rule-based, not an LLM
              │                                 │   judgment call, consistent
              │                                 │   with the hard-rule-before-
              │                                 │   LLM pattern across every
              │                                 │   Coverline workflow)
              └────────────┬─────────────────┘
                            ▼
              ┌───────────────────────────┐
              │ LLM Draft Generation Layer     │  (grounded, citation-
              │                                 │   enforced per FR-6)
              └────────────┬─────────────────┘
                            ▼
              ┌───────────────────────────┐
              │ Compliance Gate                 │──► No Market Found drafts
              │ (No Market Found only,          │    held for compliance
              │  per FR-8)                      │    review before reaching
              └────────────┬─────────────────┘    standard review queue
                            ▼
              ┌───────────────────────────┐
              │ Broker Review Queue             │◄──── Edit distance, send
              │ (embedded in submission record) │       actions logged here
              └────────────┬─────────────────┘
                            ▼
              ┌───────────────────────────┐
              │ Send Action (manual click        │  (never automatic, per
              │  required, per FR-20)             │   FR-20's guarantee)
              └────────────┬─────────────────┘
                            ▼
              ┌───────────────────────────┐
              │ No-Response Monitor             │  (watches against carrier-
              │ (per-carrier acceptance-window  │   specific windows per
              │  aware, per FR-11)                │   FR-11, not a fixed
              │                                    │   default)
              └───────────────────────────────┘
```

**Key architectural point:** this workflow is, as expected, the lightest
build in the Wholesale/E&S vertical so far — no new extraction, minimal
new data (retail agent relationship context, which may already be
available via the same CRM connector used elsewhere). The real
engineering and product care is concentrated entirely in the Tone/Framing
Rule Selection layer and the Compliance Gate, exactly mirroring where the
real complexity lived in the MGA Broker Communication build.

---

## 9. Risks & Open Questions

| Risk | Mitigation / Owner |
|---|---|
| Carrier-name-disclosure question (RA-TN-06) is unresolved and is a launch-blocking compliance decision, not a product default | Must be raised explicitly with the design partner's compliance/legal function during discovery — do not default to either full disclosure or full suppression without their input; the conservative aggregate-framing default in this PRD is a starting point for that conversation, not a final answer |
| Quote/Terms Summary pricing-justification quality depends entirely on whether upstream data (the manually-logged quote_context in v1) is actually populated with real reasoning, not just a number | Since Quote Comparison isn't built yet, v1's manual-input path (FR-2) relies on the broker themselves providing the pricing context accurately — confirm this is a realistic expectation during discovery, or consider whether this communication type should wait until the automated Quote Comparison workflow exists to supply it more reliably |
| No Market Found may be a more common outcome in this vertical than in MGA workflows, especially early on with a narrow initial carrier panel (same risk flagged in the Market Matching PRD) — meaning this highest-sensitivity communication type could see disproportionately heavy use relative to how much v1 testing time it receives | Weight pre-launch eval effort accordingly — don't let this draft type get proportionally less testing just because it's one of six types; it may be the most frequently triggered one in early usage |
| Tenure-aware explanatory depth (RA-TN-10) requires relationship data that may not be reliably tracked, same risk flagged in the MGA equivalent's Section 9 | Same mitigation — confirm data availability during discovery, default to neutral tone gracefully when unavailable, per FR-3 |

---

## 10. Rollout Plan

1. **Discovery (1 week):** confirm retail agent relationship data availability, and — critically — resolve the carrier-name-disclosure compliance question with the design partner's legal function before any No Market Found draft is used live, even in shadow mode.
2. **Build v0 (2-3 weeks):** Trigger Classification, Retail Agent Context Retrieval, Tone/Framing Rule Selection, Draft Generation Layer, Compliance Gate, review queue UI extension — mirrors the MGA Broker Communication PRD's build scope and timeline closely.
3. **Shadow mode (1-2 weeks):** generate drafts for real triggers, brokers continue drafting manually, compare AI drafts to what was actually sent.
4. **Live pilot (3-4 weeks):** drafts enter the real review queue, Section 2.3 metrics tracked weekly, with particular attention to the two hardest categories (No Market Found, Quote/Terms Summary).
5. **Go/no-go review:** against Section 2.3 criteria, with the zero-unauthorized-carrier-disclosure gate treated as non-negotiable regardless of how well other metrics perform.

---

*This document defines v1 scope only. Auto-send capability, automated Quote Comparison integration, and any resolution of the carrier-name-disclosure question that moves beyond the conservative default in this PRD should be treated as deliberate follow-on decisions — the last of these specifically requires signed-off compliance input, not an engineering judgment call.*
