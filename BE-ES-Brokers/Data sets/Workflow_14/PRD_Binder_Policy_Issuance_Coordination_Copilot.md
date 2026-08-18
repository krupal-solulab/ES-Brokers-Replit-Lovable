# PRD: Binder & Policy Issuance Coordination Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Draft for engineering scoping
**Owner:** [Product]
**Last updated:** 2026-07-16
**Depends on:** Quote Comparison & Recommendation (v1) — this workflow begins the moment a broker selects a quote to bind, and it feeds two triggers into the Retail Agent Communication Copilot (Placement Confirmation, and a new Policy Documents Delivered trigger this PRD introduces). This is the workflow that closes the full placement lifecycle: submission → match → package → quote → compare → **bind and issue**.

---

## 1. Problem Statement

Once a broker decides which quote to bind, the placement isn't actually finished — it enters a coordination phase that spans the carrier (confirming the bind, eventually issuing the full policy), the broker (tracking subjectivities through to clearance, both before and after binding), and the retail agent (who needs to know coverage is confirmed, and eventually needs the actual policy documents). This phase is where real, costly errors happen in practice: a carrier's bind confirmation can quietly differ from what was quoted, a pre-bind subjectivity can get missed under time pressure, a post-bind ongoing obligation (like a required loss control report) can get forgotten once the immediate urgency of binding has passed, and — most seriously — an issued policy document can simply not match what was actually bound and communicated to the client, an error that can go undetected for months if nobody is actively checking.

**Goal of v1:** Coordinate the bind request, track pre-bind subjectivity clearance (blocking the bind order when material items remain open), reconcile carrier bind confirmations and issued policy documents against what was actually agreed, monitor policy issuance timelines, and track post-bind ongoing obligations — surfacing discrepancies and overdue items proactively rather than waiting for someone to notice.

**Explicitly not the goal of v1:** Automatically sending a bind order to a carrier, resolving a discrepancy autonomously, or negotiating a correction with a carrier on the broker's behalf.

---

## 2. Scope of v1

### 2.1 In scope
- Bind order generation from a broker's Quote Comparison selection (Section 6, BI-01)
- Pre-bind subjectivity clearance tracking with blocking logic for material, unresolved items (BI-02)
- Carrier bind confirmation reconciliation against requested terms (BI-03)
- Policy issuance timeline monitoring, using each carrier's own stated timeline as the threshold (BI-04)
- Issued policy document reconciliation against confirmed bind terms (BI-05) — the single highest-value check in this workflow
- Downstream trigger gating for Retail Agent Communication (BI-06), including a new Policy Documents Delivered trigger type
- Post-bind ongoing obligation tracking, distinct from pre-bind blockers (BI-07)
- Human sends every bind order and resolves every flagged discrepancy — no automated carrier-facing action

### 2.2 Explicitly out of scope for v1
- Automatically sending the bind order to the carrier — the broker reviews and sends manually, same permanent boundary as every prior Coverline workflow
- Automatically resolving a BI-03 or BI-05 discrepancy — the system flags and presents both values; a human decides which is correct and takes the corrective action
- Negotiating a policy correction with a carrier on the broker's behalf
- Multi-policy/account-level coordination (a single insured with multiple bound policies across different carriers/lines) — v1 treats each bind independently; account-level rollup is a future extension
- Certificate of insurance generation or ongoing certificate-request handling for the insured's own downstream contractual needs — out of scope, a distinct future workflow if pursued at all

### 2.3 Success criteria (must hit before expanding scope)
- **Zero false-clean confirmations:** 0% of bind confirmations or issued policies with a material term mismatch should be marked as reconciled/clean in the pre-launch eval — this is the single most important quality gate in this PRD, given the real financial/coverage-gap consequences of a missed discrepancy (per Scenario 06's wind/hail deductible case)
- **Zero incorrectly blocked binds:** 0% of binds with only routine (non-material) or post-bind-ongoing subjectivities should be incorrectly held as BLOCKED — this is the mirror-image failure mode to the above, and both directions matter equally
- **Overdue issuance detection recall:** 100% of policies exceeding their carrier's own stated issuance timeline must be flagged — hard gate, consistent with every timing-sensitive rule elsewhere in this vertical
- **Downstream trigger accuracy:** 0 instances of Placement Confirmation or Policy Documents Delivered firing while an unresolved BI-03 or BI-05 discrepancy exists — hard gate per BI-06

---

## 3. Users & Personas

| Persona | Role in this workflow |
|---|---|
| **Wholesale Broker / Production Underwriter** (primary user) | Sends bind orders, resolves flagged discrepancies, tracks subjectivity clearance, forwards final policy documents |
| **Brokerage Principal / Managing Partner** (secondary) | Cares about transaction accuracy and E&O exposure — this workflow's reconciliation checks are directly protective of the areas that generate wholesale brokerage E&O claims |
| **Retail Agent** (indirect, downstream recipient) | Receives Placement Confirmation and, eventually, final policy documents — only once this workflow has verified both are accurate |
| **Carrier Underwriting/Binding Team** (indirect, external party) | Issues bind confirmations and policy documents that this workflow actively verifies rather than trusts by default |

---

## 4. End-to-End Workflow

```
1. Broker selects a quote to bind from Quote Comparison's output
2. System checks pre-bind subjectivity status (inherited classification
   from Quote Comparison's QC-02) — any material, unresolved item BLOCKS
   bind order generation (BI-02)
3. Once all material pre-bind subjectivities are cleared, system
   generates a bind order matching the selected quote's terms exactly
   (BI-01)
4. Broker reviews and sends the bind order to the carrier manually
5. Carrier responds with a bind confirmation (binder number + terms)
6. System reconciles the carrier's confirmation against the originally
   requested terms (BI-03) — any material mismatch is flagged, both
   values presented, broker must explicitly resolve before this is
   treated as a clean bind
7. Upon clean confirmation (or broker-resolved discrepancy), system:
   a. Initiates policy issuance monitoring against the carrier's stated
      timeline (BI-04)
   b. Establishes ongoing tracking for any post-bind subjectivities
      (BI-07), independent of the bind confirmation's own status
   c. Fires the Placement Confirmation trigger to Retail Agent
      Communication (BI-06)
8. System monitors for policy document arrival; if the carrier's stated
   timeline is exceeded with no documents received, generates a
   proactive overdue alert (BI-04)
9. When policy documents arrive, system reconciles them against the
   confirmed bind terms (BI-05) — any material mismatch is flagged and
   blocks the Policy Documents Delivered trigger until resolved
10. Upon clean reconciliation, system fires Policy Documents Delivered
    to Retail Agent Communication (BI-06), and forwards final policy
    documents
11. Post-bind ongoing obligations (BI-07) continue to be tracked with
    reminders on their own timeline, independent of steps 8-10
12. System logs every step, every discrepancy found and how it was
    resolved, for the Feedback/Eval Store — this is also the most
    E&O-relevant audit trail in the whole vertical, since it directly
    documents that bind and issuance terms were actively verified, not
    assumed
```

**Design principle, extended further than any prior workflow in this
vertical:** every previous Coverline workflow's core discipline was "the
system never fabricates, the human always approves." This workflow adds
a second, equally important discipline: **the system never assumes an
external party's document is correct just because it's official.** Both
disciplines matter, and this PRD is where the second one does the most
concrete, protective work.

---

## 5. Functional Requirements

### 5.1 Bind Order Generation

- **FR-1:** Generate a bind order from the broker's selected quote (Quote Comparison output), matching its terms exactly — premium, limits, deductible, effective date — with no re-derivation or summarization that could introduce drift (BI-01).
- **FR-2:** Bind order generation must check pre-bind subjectivity status first (per FR-3) and must not be presented as ready-to-send while material items remain open.

### 5.2 Pre-Bind Subjectivity Tracking

- **FR-3:** Inherit subjectivity classification (routine vs. material, and — new in this workflow — pre-bind vs. post-bind-ongoing lifecycle stage) directly from Quote Comparison's QC-02 output; do not re-classify independently, per the consistency principle in the Rule Engine Interpretation Guide.
- **FR-4:** Any subjectivity classified `material` and `PRE_BIND` that remains unresolved must set the bind order status to `BLOCKED`, using the same three-state pattern (`READY` / not applicable here since there's no gap-tolerant middle state for a bind the way there was for a submission package / `BLOCKED`) established elsewhere in this vertical.
- **FR-5:** The review interface must clearly show which specific subjectivity is blocking, not just a generic "not ready" status, consistent with the specificity standard established across every Coverline workflow.

### 5.3 Carrier Bind Confirmation Reconciliation

- **FR-6:** Extract structured terms from the carrier's bind confirmation (binder number, premium, limits, deductible, effective date) — this reuses the same unstructured-email-extraction challenge already flagged as a real engineering cost in the Quote Comparison PRD, since bind confirmations come in the same free-text carrier-email format as quotes.
- **FR-7:** Reconcile every extracted field against the originally requested bind terms (per FR-1); any mismatch on premium, limits, deductible, or effective date must produce a `DISCREPANCY_FLAGGED` state, never a silent auto-accept, per BI-03.
- **FR-8:** When a discrepancy is found, present both the requested and confirmed values side by side and require explicit broker action (acknowledge carrier's version / flag as carrier error / other resolution) before the bind is treated as clean — the system must never auto-resolve in favor of either value.

### 5.4 Policy Issuance Monitoring

- **FR-9:** Extract the carrier's stated issuance timeline from the bind confirmation where given; if not stated, default to a configurable standard assumption (e.g., 45 days) flagged as an assumption, not a confirmed carrier commitment.
- **FR-10:** Run an ongoing, scheduled check (not just at bind time) comparing elapsed time since bind confirmation against the applicable timeline; generate a proactive alert once exceeded with no policy documents logged as received, per BI-04.
- **FR-11:** This monitoring must continue independently of other workflow steps — a bind with no discrepancies and no material subjectivities still needs its issuance timeline tracked.

### 5.5 Issued Policy Reconciliation

- **FR-12:** Extract structured terms from the issued policy document (declarations page) once received — premium, limits, deductibles, effective date, and any endorsements referenced.
- **FR-13:** Reconcile every extracted field against the **confirmed bind terms** (not the original request, and not the original quote — the bind confirmation, including any broker-resolved BI-03 discrepancy, is the correct baseline per the Rule Engine Interpretation Guide's note on BI-05).
- **FR-14:** Any material mismatch must produce a `POLICY_DISCREPANCY_FLAGGED` state and must block the Policy Documents Delivered downstream trigger (FR-17) until resolved — treated with the same seriousness as the zero-false-positive gates in Market Matching and Package Assembly, given the direct coverage-gap risk to the insured.
- **FR-15:** This check must be genuinely field-by-field, not a holistic "looks about right" comparison — Scenario 06's wind/hail deductible discrepancy is exactly the kind of single-field mismatch that a less rigorous check could miss while correctly matching every other field.

### 5.6 Post-Bind Ongoing Obligation Tracking

- **FR-16:** Any subjectivity classified `POST_BIND_ONGOING` must be tracked as a persistent, dated task independent of bind confirmation or policy issuance status — it must not block anything in this workflow, but it must also not be dropped or lost once the bind is confirmed, per BI-07.
- **FR-17:** Generate reminders at configurable intervals before an ongoing obligation's deadline (e.g., 15 and 5 days prior, per the pattern modeled in Scenario 04) — surfaced to the broker, not automatically actioned.

### 5.7 Downstream Trigger Integration

- **FR-18:** Fire the Retail Agent Communication Copilot's Placement Confirmation trigger only once BI-03 reconciliation is clean (or an identified discrepancy has been explicitly broker-resolved) — never on an unresolved discrepancy, per BI-06.
- **FR-19:** Introduce a new Policy Documents Delivered trigger type to the Retail Agent Communication Copilot (this extends that PRD's Section 5.2 communication-type mapping — flag as a coordinated follow-on scope item for that workflow, not something this PRD can fully specify unilaterally) — fire only once BI-05 reconciliation is clean.
- **FR-20:** Both triggers must carry the verified, reconciled terms (not the originally requested terms) as their grounding data, so downstream communications to the retail agent reflect what's actually true.

### 5.8 Human Review Interface

- **FR-21:** Unified status view per bound account: pre-bind subjectivity checklist, bind confirmation reconciliation status, policy issuance timeline/monitoring status, post-bind ongoing obligations with due dates — one coordinated view spanning the whole post-selection lifecycle, not fragmented across separate screens (per BI-06's coordination intent).
- **FR-22:** Discrepancies (BI-03, BI-05) must be visually and positionally distinct from routine status updates — a broker should never have to dig to find an unresolved discrepancy.
- **FR-23:** One-click actions for discrepancy resolution: Accept carrier's version / Flag as carrier error, request correction / Escalate to principal — logged for the feedback loop.
- **FR-24:** All broker actions logged, consistent with every prior Coverline workflow's pattern.

### 5.9 Non-Functional Requirements

- **FR-25:** Bind order generation and confirmation reconciliation: target < 5 minutes processing time, consistent with the lighter-weight workflows in this vertical.
- **FR-26:** Policy issuance and post-bind obligation monitoring must run as ongoing scheduled processes (same architectural pattern as the Quote Validity Monitor from the Quote Comparison PRD and the Renewal Trigger Service from the MGA Renewal Management PRD) — this is now the third workflow in the overall Coverline build requiring this execution model, worth ensuring the underlying scheduled-job infrastructure is shared/reusable rather than rebuilt each time.
- **FR-27:** Same data retention, encryption, and access-control requirements as every prior Coverline workflow — this workflow's audit trail is particularly significant given its direct relevance to E&O documentation, so retention policy here should be confirmed with the design partner's compliance function as at least as strict as anywhere else in the system, not more lenient.

---

## 6. Rule Engine

**See the companion document, `RULE_ENGINE_INTERPRETATION_GUIDE.md`, for
full interpretation notes and worked examples.** Summary:

| Rule ID | Rule | Type |
|---|---|---|
| BI-01 | Bind order composition accuracy | Fidelity check against broker's selection |
| BI-02 | Pre-bind subjectivity clearance and blocking | Inherited classification from QC-02, blocks bind order |
| BI-03 | Carrier bind confirmation reconciliation | **Never trust external confirmation by default** |
| BI-04 | Policy issuance timeline monitoring | Ongoing scheduled check, carrier's own stated timeline as threshold |
| BI-05 | Issued policy vs. bound terms reconciliation | **Highest-value check in this PRD — never trust issued documents by default** |
| BI-06 | Downstream trigger gating | Only fires on verified-clean states |
| BI-07 | Post-bind ongoing obligation tracking | Persistent, non-blocking, reminder-driven |

**All timelines and thresholds (issuance timeline defaults, reminder
intervals) are placeholders**, consistent with every rules document in
this project, and must be validated with the design partner during
discovery — particularly BI-04's default assumption when a carrier
doesn't explicitly state an issuance timeline, which should be
calibrated against real historical data on how long each carrier
actually takes, not a generic industry guess.

---

## 7. Data Schemas

### 7.1 Bind Coordination Record Schema

```json
{
  "bind_id": "string",
  "submission_id": "string",
  "named_insured": "string",
  "carrier_id": "string",
  "carrier_name": "string",
  "requested_bind_terms": {"premium": "currency", "limits": "string", "deductible": "currency", "effective_date": "date"},
  "pre_bind_subjectivities": [
    {"description": "string", "materiality": "routine | material", "status": "cleared | open"}
  ],
  "bind_order_status": "BLOCKED | READY | SENT",
  "carrier_confirmation": {
    "binder_number": "string, null until received",
    "confirmed_terms": {"premium": "currency", "limits": "string", "deductible": "currency", "effective_date": "date"},
    "reconciliation_status": "PENDING | CLEAN | DISCREPANCY_FLAGGED | BROKER_RESOLVED",
    "discrepancy_detail": [{"field": "string", "requested": "string", "confirmed": "string"}]
  },
  "policy_issuance": {
    "carrier_stated_timeline_days": "integer, null if not stated (assumption used instead)",
    "expected_by_date": "date",
    "documents_received": "boolean",
    "overdue_alert_fired": "boolean"
  },
  "issued_policy_reconciliation": {
    "status": "NOT_YET_RECEIVED | PENDING | CLEAN | POLICY_DISCREPANCY_FLAGGED | BROKER_RESOLVED",
    "discrepancy_detail": [{"field": "string", "bound": "string", "issued": "string"}]
  },
  "post_bind_ongoing_obligations": [
    {"description": "string", "due_date": "date", "status": "open | completed", "reminders_sent": ["list of dates"]}
  ],
  "downstream_triggers_fired": {
    "placement_confirmation": "boolean",
    "policy_documents_delivered": "boolean"
  },
  "status_log": [{"action": "string", "timestamp": "datetime", "user": "string"}]
}
```

---

## 8. System Architecture (Level 2)

```
┌───────────────────────────┐
│ Quote Comparison Output       │  (existing — broker's quote selection,
│ (broker's bind selection)     │   inherited subjectivity classification)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Pre-Bind Subjectivity Gate    │  (BI-02 — blocks bind order generation
│                                 │   on unresolved material items)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Bind Order Generator           │  (BI-01)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Broker Review & Manual Send    │
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Carrier Bind Confirmation      │  (NEW extraction target — same
│ Extraction                     │   unstructured-email challenge as
│                                 │   Quote Comparison's carrier responses)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Bind Confirmation                │  (BI-03 — never auto-trust, present
│ Reconciliation Engine            │   discrepancies for broker resolution)
└────────────┬─────────────────┘
             │
             ├──────────────────────────────┐
             ▼                                ▼
┌───────────────────────────┐  ┌───────────────────────────┐
│ Policy Issuance Monitor        │  │ Post-Bind Ongoing Obligation  │
│ (BI-04 — scheduled, ongoing)   │  │ Tracker (BI-07 — scheduled,    │
└────────────┬─────────────────┘  │  ongoing, reminder-driven)      │
             ▼                      └───────────────────────────┘
┌───────────────────────────┐
│ Issued Policy Extraction &      │  (NEW extraction target — policy
│ Reconciliation (BI-05)           │   declarations pages)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Downstream Trigger Gate         │  (BI-06 — fires Placement
│                                   │   Confirmation / Policy Documents
│                                   │   Delivered only on verified-clean
│                                   │   states)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Retail Agent Communication      │      │ Broker Review Interface        │
│ Copilot (existing, extended     │      │ (unified status view, per      │
│  per FR-19)                      │      │  FR-21)                         │
└───────────────────────────────┘      └───────────────────────────────┘
```

**Key architectural point:** this workflow introduces two genuinely new
extraction targets (carrier bind confirmations, issued policy
declarations pages) on top of the carrier-response extraction challenge
already flagged in Quote Comparison — and it introduces the vertical's
third instance of ongoing/scheduled monitoring (alongside Quote
Comparison's validity tracking and, architecturally, the MGA Renewal
Trigger Service). Budget for both: real extraction engineering effort
comparable to Quote Comparison's, and shared scheduled-job
infrastructure rather than a third bespoke implementation.

---

## 9. Risks & Open Questions

| Risk | Mitigation / Owner |
|---|---|
| Carrier bind confirmations and issued policy documents will have as much (or more) format variance as carrier quote responses, since there's even less standardization at the binding/issuance stage than at the quoting stage | Treat as a continuation of the same extraction-variance risk flagged in the Quote Comparison PRD — sample real bind confirmations and policy declarations pages from the design partner's history during discovery before committing to a timeline |
| FR-19's new Policy Documents Delivered trigger requires a coordinated update to the Retail Agent Communication Copilot's PRD, not just this one — this PRD cannot fully specify that trigger's tone/framing rules unilaterally | Treat this as a joint scope item; when this workflow is actually built, revisit the Retail Agent Communication PRD alongside it rather than assuming this PRD's brief mention is sufficient specification on its own |
| BI-05's policy reconciliation is the highest-value and highest-stakes check in this PRD, but also depends on reliable extraction from an even less standardized document type (policy declarations pages vary enormously by carrier) than anything else built so far in this vertical | This deserves outsized eval investment relative to its apparent simplicity — treat Scenario 06 as a mandatory, non-skippable release gate, similar to how Package Assembly's PA-02 auto-fill boundary was treated in that PRD |
| Discrepancy resolution (BI-03, BI-05) currently assumes a broker can always determine which version (requested vs. confirmed, or bound vs. issued) is correct — in practice this may require going back to the carrier for clarification, which is outside this workflow's scope | Confirm with the design partner during discovery what the realistic resolution workflow looks like in practice, and make sure the UI (FR-23) supports "escalate to carrier for clarification" as a real resolution path, not just "accept one value or the other" |
| Three concurrent ongoing-monitoring systems now exist across the vertical (Quote Validity, Policy Issuance, Post-Bind Obligations) — worth confirming these don't need to interact with each other in ways not yet modeled (e.g., does a post-bind obligation deadline ever get affected by a policy issuance delay?) | Flag as a discovery/architecture question rather than assuming full independence, similar to the cross-carrier-dependency question flagged in the Package Assembly PRD |

---

## 10. Rollout Plan

1. **Discovery (2 weeks):** sample real bind confirmations and issued policy declarations pages from the design partner's history to assess extraction variance, confirm realistic discrepancy-resolution workflows with brokers, coordinate the Policy Documents Delivered trigger scope with the Retail Agent Communication Copilot.
2. **Build v0 (4-5 weeks — comparable to Quote Comparison's timeline, given similar new-extraction-target complexity):** Bind Order Generator, Pre-Bind Subjectivity Gate, Bind Confirmation Reconciliation Engine, Policy Issuance Monitor, Issued Policy Extraction & Reconciliation, Post-Bind Obligation Tracker, unified status UI.
3. **Shadow mode (2-3 weeks):** run against real in-flight binds in parallel with brokers' normal manual process, with particular attention to whether BI-03/BI-05 reconciliation catches anything a broker would have otherwise missed.
4. **Live pilot (4 weeks):** system output enters the real review queue, Section 2.3 metrics tracked weekly, with the two zero-false-clean gates (BI-03, BI-05) treated as non-negotiable throughout.
5. **Go/no-go review:** against Section 2.3 criteria — only then consider Endorsement Processing or Renewal Remarketing (both now have real bound-policy data to work against, per the sequencing rationale established in the prior roadmap discussion) as the next builds.

---

*This document defines v1 scope only. Automated carrier-facing bind submission, autonomous discrepancy resolution, certificate of insurance handling, and multi-policy account-level coordination should be treated as new PRD scope — and per Section 9, the Policy Documents Delivered trigger specifically requires coordinated scoping with the Retail Agent Communication Copilot before either PRD should be considered fully specified on this point.*
