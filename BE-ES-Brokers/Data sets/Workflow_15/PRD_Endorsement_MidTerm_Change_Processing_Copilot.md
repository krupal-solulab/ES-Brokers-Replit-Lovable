# PRD: Endorsement / Mid-Term Change Processing Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Draft for engineering scoping
**Owner:** [Product]
**Last updated:** 2026-07-16
**Depends on:** Binder & Policy Issuance Coordination (v1) — this workflow operates on already-bound policy records that workflow produces, and inherits its core discipline (never trust a carrier's issued document by default) into a new context. It also produces a new communication trigger for the Retail Agent Communication Copilot, similar in spirit to that PRD's own extension in the prior workflow.

---

## 1. Problem Statement

Once a policy is bound, the insured's needs don't stop changing — a new contract requires an additional insured, a business acquires a new location, a client demands higher limits, operations expand into a new service line. Retail agents send these requests to the wholesale broker expecting quick, accurate handling, but not all mid-term changes are the same kind of request: some are routine administrative updates a carrier processes without a second look, and others are material changes that touch the carrier's actual risk appetite and require real underwriting judgment — sometimes revealing that the requested change isn't something the current carrier will even write. Treating every endorsement request the same way — either rubber-stamping everything as routine or escalating everything as if it needs full underwriting review — produces bad outcomes in both directions: unnecessary friction on simple requests, and dangerous under-scrutiny on requests that actually change the risk profile the carrier agreed to when they bound the account.

**Goal of v1:** Classify each mid-term change request by type and materiality, re-check carrier appetite when a change touches class, state, or severity exposure, draft the endorsement request to the carrier with correct premium-impact and proration handling, and reconcile the carrier's issued endorsement against what was actually requested before confirming anything to the retail agent.

**Explicitly not the goal of v1:** Automatically approving or processing any endorsement without human review, calculating final pro-rata premium amounts independently of the carrier, or handling a change so material it effectively requires a new placement (Scenario 03's solar-installation case) beyond flagging that it may need to become one.

---

## 2. Scope of v1

### 2.1 In scope
- Endorsement/change request classification by type and materiality (Section 6, EP-01)
- Appetite recheck for changes touching class, state, or severity exposure, with an explicit three-outcome model (within appetite / outside appetite / genuinely unknown) — EP-02
- Premium impact flagging (premium-bearing vs. not), without independently calculating final amounts — EP-03
- Endorsement request drafting to the carrier, matching the retail agent's request exactly — EP-04
- Issued endorsement reconciliation against the original request, including item-level checking for multi-part requests — EP-05
- Proration input validation (correct timing inputs surfaced, not an independent premium calculation) — EP-06
- Human reviews and sends every endorsement request, and resolves every flagged discrepancy or appetite-unknown case

### 2.2 Explicitly out of scope for v1
- Automatically processing or approving any endorsement request without broker review — same permanent boundary as every prior Coverline workflow
- Independently calculating final pro-rata premium amounts — this remains the carrier's determination; v1 surfaces correct timing inputs and flags premium-bearing status, never presents an assumed dollar figure as confirmed
- Full re-placement handling when a change effectively requires a new submission (Scenario 03's outcome) — v1 flags this possibility and recommends it, but the actual re-placement would run through Submission Market Matching as a new instance, not through this workflow
- Multi-policy coordination (a change affecting more than one bound policy for the same insured simultaneously) — v1 treats each bound policy independently
- Automated retail agent notification of endorsement status changes beyond the two defined trigger points (request acknowledged, endorsement confirmed/reconciled) — ongoing status inquiries are handled manually in v1

### 2.3 Success criteria (must hit before expanding scope)
- **Zero misclassified appetite-unknown cases:** 0% of changes touching a class/state not clearly on a carrier's accepted or excluded list should be auto-processed as routine or silently rejected — this must always surface as an explicit open question, mirroring the seriousness of Market Matching's zero-false-positive-hard-match gate
- **Zero missed material-change appetite flags:** 100% of changes that materially affect severity, class, or state exposure must trigger the appetite recheck (EP-02) — hard gate
- **Zero false-clean endorsement reconciliations:** 0% of issued endorsements with an item-level mismatch against the original request (per Scenario 05's pattern) should be marked as fully reconciled — direct extension of Binder & Policy Issuance's BI-05 gate into this workflow
- **Routine-classification accuracy:** ≥90% agreement between the system's routine/review classification and what an experienced broker would independently determine, measured against a held-out historical sample — the one softer metric in this list, since materiality judgment has some legitimate variance even among experienced brokers

---

## 3. Users & Personas

| Persona | Role in this workflow |
|---|---|
| **Wholesale Broker / Production Underwriter** (primary user) | Reviews classification, resolves appetite-unknown flags, sends endorsement requests, resolves reconciliation discrepancies |
| **Brokerage Principal / Managing Partner** (secondary) | Cares about E&O exposure from mishandled material changes and about turnaround time on routine requests |
| **Carrier Underwriting Team** (indirect, external party) | Receives requests and makes the actual appetite/pricing determination on material changes — this workflow prepares the request and interprets the response, it doesn't replace the carrier's judgment |
| **Retail Agent** (indirect, downstream recipient) | Originates the change request and eventually receives confirmation — via the Retail Agent Communication Copilot's new trigger from this workflow |

---

## 4. End-to-End Workflow

```
1. Retail agent sends a mid-term change request via email for an
   already-bound policy (tracked via Binder & Policy Issuance's records)
2. System ingests and extracts the structured change request: type,
   detail, requested effective date
3. System classifies the request (EP-01): routine, or underwriting-
   review-required — based on change TYPE first, then materiality
   within type
4. If the change touches class, state, or severity exposure, system
   runs the appetite recheck (EP-02) against the bound carrier's known
   profile, producing one of three outcomes: within appetite, outside
   appetite, or genuinely unknown
5. System flags premium impact (EP-03) — premium-bearing or not — and,
   if premium-bearing and mid-term, surfaces the correct proration
   inputs (EP-06) without calculating a final figure itself
6. System drafts the endorsement request to the carrier, matching the
   retail agent's request exactly (EP-04)
7. Broker reviews:
   a. For routine, in-appetite requests: quick review and send
   b. For underwriting-review-required or appetite-unknown requests:
      broker sends with full context to the carrier's underwriting
      team, not as a standard endorsement processing request
   c. For appetite-unknown cases resolved as "outside appetite": broker
      may need to initiate a new Submission Market Matching pass for
      just the new operations/exposure, outside this workflow's scope
8. Carrier issues the endorsement (or responds with a decision on a
   material change)
9. System reconciles the issued endorsement against the original
   request, item by item for multi-part requests (EP-05)
10. Upon clean reconciliation, system fires an endorsement-confirmed
    trigger to Retail Agent Communication; on a discrepancy, this is
    held until broker-resolved, consistent with the Binder & Policy
    Issuance PRD's trigger-gating discipline
11. System logs every step, classification decision, and reconciliation
    outcome for the Feedback/Eval Store — including the appetite-
    unknown resolutions, which are a real signal for the eventually-
    deferred Carrier Appetite Intelligence workflow, consistent with
    how Quote Comparison's QC-03 logs declination-consistency signals
    without acting on them
```

**Design principle:** this workflow inherits two disciplines from
earlier PRDs in this vertical, applied together for the first time — the
never-assume-appetite-fit-from-an-absent-data-point discipline from
Market Matching, and the never-trust-an-external-party's-issued-document
discipline from Binder & Policy Issuance. Both matter here because a
mid-term change request sits at the intersection of "does this still fit
what the carrier agreed to" and "did the carrier actually do what was
asked" — the two hardest questions in the whole vertical, now appearing
together in a single workflow.

---

## 5. Functional Requirements

### 5.1 Change Request Ingestion & Extraction

- **FR-1:** Ingest and classify incoming endorsement/change request emails, associating each with the correct bound policy record (matching on named insured + carrier + bind ID, consistent with matching patterns established elsewhere in this vertical).
- **FR-2:** Extract the structured change request: type (from a defined taxonomy — additional insured, limit increase, location addition, operations/class addition, headcount/exposure update, other), specific detail, and requested effective date.

### 5.2 Classification

- **FR-3:** Classify each request as `ROUTINE` or `UNDERWRITING_REVIEW_REQUIRED` using a type-based-first approach (per EP-01's interpretation note) — certain types are never purely routine (limit increases, class/operations additions, location additions) regardless of apparent size; certain types are typically routine (additional insured endorsements, contact/address updates) unless a specific materiality signal within that type suggests otherwise.
- **FR-4:** For borderline cases (per Scenario 06's headcount-change pattern), surface both percentage change and absolute exposure change — never classify materiality on percentage alone, since this can be misleading at small account scale.

### 5.3 Appetite Recheck

- **FR-5:** For any request touching class, state, or severity exposure, run the appetite recheck against the bound carrier's Carrier Appetite Profile (reusing the schema established in Market Matching).
- **FR-6:** This check must produce one of three explicit outcomes — `WITHIN_APPETITE`, `OUTSIDE_APPETITE`, or `APPETITE_UNKNOWN` — never collapsing the third case into either of the first two. An `APPETITE_UNKNOWN` result must be presented as an open question requiring direct carrier confirmation, never auto-processed as if it were a confirmed fit and never auto-rejected as if it were a confirmed exclusion.
- **FR-7:** When a request results in `OUTSIDE_APPETITE` or an `APPETITE_UNKNOWN` that the carrier ultimately declines, the system should flag that this may need to become a new Submission Market Matching instance rather than an endorsement, per Section 2.2's scope boundary — a recommendation to the broker, not an automated handoff in v1.

### 5.4 Premium Impact & Proration

- **FR-8:** Flag whether a request is typically premium-bearing based on change type, without asserting a specific dollar amount — this flag informs the endorsement request draft (which should explicitly ask the carrier to quote the pro-rata adjustment) rather than presenting an assumed figure.
- **FR-9:** For premium-bearing, mid-term requests, surface the correct proration inputs (days elapsed in term, days remaining, total term length) alongside the request — this is informational support for the carrier's own calculation, not an independent premium computation by Coverline.
- **FR-10:** Flag any unusual timing pattern in the requested effective date (e.g., requested effective date in the past, or a request arriving very close to policy expiration where an endorsement might not be the appropriate mechanism) rather than processing every timing situation with undifferentiated scrutiny — per EP-06's control-case principle from Scenario 06.

### 5.5 Endorsement Request Drafting

- **FR-11:** Draft the endorsement request to the carrier, matching the retail agent's original request completely and exactly — for multi-part requests (e.g., two additional insureds in one request), every part must be explicitly itemized in the drafted request, not summarized in a way that risks losing an item, per EP-04.
- **FR-12:** Underwriting-review-required and appetite-unknown requests must be drafted differently from routine requests — framed as a submission for underwriting judgment with full supporting context (current bound terms, relevant loss history where applicable), not as a standard "please process this endorsement" request, per the distinction tested in Scenario 02.

### 5.6 Issued Endorsement Reconciliation

- **FR-13:** Extract structured terms from the carrier's issued endorsement confirmation, reusing the same unstructured-email-extraction approach established for bind confirmations in the Binder & Policy Issuance PRD.
- **FR-14:** Reconcile the issued endorsement against the original request **item by item** for multi-part requests — per EP-05, a request with multiple components (e.g., two additional insureds) must be checked component by component, not with a single holistic "was something issued" check that could miss a partial fulfillment, per Scenario 05.
- **FR-15:** Any discrepancy — full or partial — must produce a flagged state and must never be silently treated as fully reconciled, consistent with the zero-false-clean-reconciliation gate in Section 2.3.

### 5.7 Downstream Integration

- **FR-16:** Fire a new endorsement-confirmed trigger to the Retail Agent Communication Copilot only once reconciliation (FR-14/FR-15) is clean or broker-resolved — same trigger-gating discipline as Binder & Policy Issuance's BI-06, and, like that PRD's Policy Documents Delivered trigger, this requires coordinated scope definition with the Retail Agent Communication Copilot's PRD rather than being fully specified unilaterally here.

### 5.8 Human Review Interface

- **FR-17:** Review queue showing: classification (routine/review-required), appetite recheck outcome where applicable, premium-impact flag, drafted request, and — once available — reconciliation status against the issued endorsement.
- **FR-18:** `APPETITE_UNKNOWN` and reconciliation-discrepancy states must be visually distinct from routine "in progress" states, consistent with the urgency/flag-type visual separation pattern established across every Coverline workflow.
- **FR-19:** One-click actions appropriate to each state: Send routine request / Send for underwriting review with context / Escalate appetite-unknown to carrier / Resolve reconciliation discrepancy.
- **FR-20:** All broker actions and classification overrides logged for the feedback loop, including appetite-unknown resolutions (per Section 4's note on future Carrier Appetite Intelligence groundwork).

### 5.9 Non-Functional Requirements

- **FR-21:** Processing time per request: target < 5 minutes for classification and draft generation, consistent with the lighter workflows in this vertical.
- **FR-22:** Same data retention, encryption, and access-control requirements as every prior Coverline workflow.

---

## 6. Rule Engine

**See the companion document, `RULE_ENGINE_INTERPRETATION_GUIDE.md`, for
full interpretation notes and worked examples.** Summary:

| Rule ID | Rule | Type |
|---|---|---|
| EP-01 | Endorsement Request Classification | Type-based first, then materiality within type |
| EP-02 | Appetite Recheck for Material Changes | Three-outcome model: within / outside / genuinely unknown |
| EP-03 | Premium Impact Determination | Flag only, never assert an unconfirmed figure |
| EP-04 | Endorsement Request Composition Accuracy | Fidelity check, item-level for multi-part requests |
| EP-05 | Issued Endorsement Reconciliation | **Never trust carrier's issued document by default** — item-level check |
| EP-06 | Effective Date / Proration Validation | Correct inputs surfaced, not an independent calculation |

**All classification thresholds are placeholders**, consistent with
every rules document in this project, and must be validated with the
design partner's brokers during discovery — particularly the type-based
routine/review taxonomy in EP-01, which should be built from real
historical endorsement request patterns, not a generic assumption about
which change types are typically routine.

---

## 7. Data Schemas

### 7.1 Endorsement Request Record Schema

```json
{
  "endorsement_request_id": "string",
  "bind_id": "string",
  "named_insured": "string",
  "carrier_id": "string",
  "requested_change": {
    "type": "additional_insured | limit_increase | location_addition | operations_class_addition | headcount_exposure_update | address_correction | other",
    "detail": "string",
    "requested_effective_date": "date"
  },
  "classification": "ROUTINE | UNDERWRITING_REVIEW_REQUIRED",
  "appetite_recheck": {
    "applicable": "boolean",
    "outcome": "WITHIN_APPETITE | OUTSIDE_APPETITE | APPETITE_UNKNOWN | NOT_APPLICABLE"
  },
  "premium_impact": {
    "premium_bearing": "boolean",
    "proration_inputs": {"days_elapsed": "integer", "days_remaining": "integer", "term_total_days": "integer"}
  },
  "drafted_request": {"body": "string", "citations": [{"claim": "string", "source": "string"}]},
  "carrier_response": {
    "endorsement_number": "string, null until issued",
    "issued_terms": "object, structure varies by change type",
    "reconciliation_status": "PENDING | CLEAN | DISCREPANCY_FLAGGED | BROKER_RESOLVED",
    "discrepancy_detail": [{"requested_item": "string", "issued_item": "string, null if missing entirely"}]
  },
  "status_log": [{"action": "string", "timestamp": "datetime", "user": "string"}]
}
```

---

## 8. System Architecture (Level 2)

```
┌───────────────────────────┐
│ Bound Policy Record            │  (existing, from Binder & Policy
│ (from Binder & Policy Issuance)│   Issuance Coordination)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Change Request Ingestion &     │  (extraction of change request from
│ Extraction                      │   retail agent email)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Classification Engine           │  (EP-01 — type-based, then
│                                  │   materiality-within-type)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Appetite Recheck Engine         │◄─────┤ Carrier Appetite Profile DB    │
│ (EP-02 — three-outcome model)   │      │ (existing, from Market         │
└────────────┬─────────────────┘      │  Matching)                      │
             ▼                          └───────────────────────────┘
┌───────────────────────────┐
│ Premium Impact & Proration      │  (EP-03, EP-06 — flags and inputs
│ Flagging                        │   only, never an asserted figure)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Endorsement Request Drafter     │  (EP-04)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Broker Review & Manual Send     │
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Issued Endorsement Extraction   │  (same unstructured-email
│ & Item-Level Reconciliation     │   extraction challenge as Binder &
│ (EP-05)                          │   Policy Issuance's confirmations)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Downstream Trigger Gate         │──────►│ Retail Agent Communication     │
│ (new trigger, per FR-16)        │      │ Copilot (extended, per FR-16)   │
└───────────────────────────────┘      └───────────────────────────────┘
```

**Key architectural point:** this is the first workflow in the vertical
that reuses substantial logic from *two* prior workflows simultaneously
(Market Matching's appetite-profile structure and three-outcome
exclusion pattern, and Binder & Policy Issuance's reconciliation
discipline) rather than extending just one. This should make it faster
to build than either of those two originals, but the engineering team
should be explicitly pointed to both prior implementations as direct
reference rather than re-deriving either pattern from scratch.

---

## 9. Risks & Open Questions

| Risk | Mitigation / Owner |
|---|---|
| EP-01's type-based routine/review taxonomy is built from general reasoning about common endorsement types, not real historical request data | Validate and likely expand this taxonomy during discovery using the design partner's actual endorsement request history — the six types modeled in the sample dataset are illustrative, not exhaustive |
| APPETITE_UNKNOWN resolutions (FR-7) may reveal a need to spin up a new Submission Market Matching pass for just the new exposure — this creates a real cross-workflow handoff that v1 only recommends rather than automates | Confirm with the design partner during discovery whether this handoff needs tighter integration in a future version, or whether manual broker-initiated handoff is sufficient for now |
| This is the second workflow (after Binder & Policy Issuance) requiring reconciliation against carrier-issued documents — extraction variance risk for issued endorsement confirmations is likely similar to bind confirmations, but should be separately validated, not assumed identical | Sample real issued endorsement documents from the design partner during discovery rather than assuming the same extraction approach transfers without adjustment |
| New endorsement-confirmed trigger (FR-16) requires coordinated scope definition with the Retail Agent Communication Copilot, same open item flagged for the Policy Documents Delivered trigger in the prior PRD | Both new trigger types should be resolved together when Retail Agent Communication is next revisited, rather than as two separate, uncoordinated follow-ups |

---

## 10. Rollout Plan

1. **Discovery (1-2 weeks):** validate the EP-01 classification taxonomy against real historical endorsement requests, sample real issued endorsement documents for extraction-variance assessment, confirm the APPETITE_UNKNOWN escalation workflow with real brokers.
2. **Build v0 (3-4 weeks — comparable to Package Assembly's timeline, given substantial reuse from Market Matching and Binder & Policy Issuance):** Classification Engine, Appetite Recheck Engine, Premium Impact/Proration Flagging, Endorsement Request Drafter, Issued Endorsement Reconciliation, review UI.
3. **Shadow mode (2 weeks):** run against real incoming endorsement requests in parallel with brokers' normal manual process.
4. **Live pilot (3-4 weeks):** system output enters the real review queue, Section 2.3 metrics tracked weekly, with particular attention to the APPETITE_UNKNOWN handling and reconciliation gates.
5. **Go/no-go review:** against Section 2.3 criteria — only then consider Renewal Remarketing (the next workflow on the vertical roadmap, and the last of the "needs real bound-policy data first" group) as the following build.

---

*This document defines v1 scope only. Automated appetite-unknown resolution, independent pro-rata premium calculation, automated re-placement handoff for out-of-appetite changes, and multi-policy coordination should be treated as new PRD scope.*
