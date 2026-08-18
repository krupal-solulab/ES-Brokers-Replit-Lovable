# PRD: Renewal Remarketing Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Draft for engineering scoping
**Owner:** [Product]
**Last updated:** 2026-07-16
**Depends on:** Binder & Policy Issuance Coordination (v1), for bound policy records; reuses Submission Market Matching's ranking engine, Quote Comparison's term-normalization discipline, and the exposure/loss-change detection logic established in the MGA Renewal Management PRD. This is the last of the workflows on the roadmap gated on having real bound-policy data to operate against.

---

## 1. Problem Statement

As a bound wholesale placement approaches renewal, the incumbent carrier typically sends renewal terms — but whether to simply accept those terms or actively shop the account elsewhere is a real decision with no single right default. Always remarketing wastes broker effort and can strain carrier relationships on accounts where shopping never produces a better outcome. Never remarketing risks leaving real savings or better terms unclaimed, and — more seriously — risks missing the signal when an incumbent's silence itself indicates they may be exiting the class or account entirely, which can leave an insured scrambling for coverage close to expiration. Today, this decision is made informally, often defaulting to whatever the broker has time for rather than a considered read of what's actually changed.

**Goal of v1:** Given a bound policy approaching renewal, detect exposure and loss-history changes, check incumbent responsiveness and appetite, and produce a graduated remarket recommendation — no remarket, a light comparison check, a full remarket, or an urgent remarket driven by incumbent non-response — grounded in the account's own data and remarketing history, not a one-size-fits-all default.

**Explicitly not the goal of v1:** Automatically executing a remarket without broker approval, automatically accepting or declining incumbent renewal terms, or making the final carrier selection when multiple options exist.

---

## 2. Scope of v1

### 2.1 In scope
- Exposure and loss-history change detection against the bound policy record, reusing the MGA Renewal Management PRD's detection logic (Section 6, RR-01/RR-02)
- Incumbent appetite recheck and non-response/silent-non-renewal detection (RR-03, RR-07)
- A graduated, four-state remarket trigger decision — not a binary flag (RR-04)
- Remarket execution via direct re-invocation of the existing Market Matching engine (RR-05)
- Comparability assessment between incumbent renewal terms and any remarketed alternatives, reusing Quote Comparison's QC-01 discipline, including flagging exception-based quotes (RR-06)
- Relationship-cost/remarketing-history weighting to avoid reflexive over-shopping (RR-08)
- Human reviews and approves every remarket decision, every comparison, and every final carrier selection

### 2.2 Explicitly out of scope for v1
- Automatically executing a remarket (sending submissions to alternative carriers) without explicit broker approval — the system recommends a remarket level, the broker initiates it
- Automatically accepting incumbent renewal terms on the broker's behalf, even in a clean NO_REMARKET case — final acceptance remains a broker action
- Negotiating revised terms with the incumbent carrier
- Multi-policy renewal coordination (an insured with several policies renewing at different times/carriers) — v1 treats each renewal independently
- Predictive appetite-exit modeling beyond the current-cycle non-response signal (RR-07) — this is informational logging only, feeding the same deferred Carrier Appetite Intelligence workflow referenced throughout this vertical's other PRDs, not an active prediction capability in v1

### 2.3 Success criteria (must hit before expanding scope)
- **Zero missed urgent triggers:** 100% of incumbent non-response situations within the configured pre-expiration window must trigger URGENT_REMARKET — hard gate, given the direct coverage-lapse risk, consistent with the seriousness given to every other timing-critical rule in this vertical
- **Graduated trigger accuracy:** ≥80% agreement between the system's four-state trigger decision (none/light/full/urgent) and what an experienced broker would independently determine, measured against a held-out historical sample — explicitly a four-way classification metric, not a binary one, since collapsing the states would hide exactly the kind of error Scenario 03 is built to catch
- **Zero misleading remarket comparisons:** 0% of incumbent-vs-alternative comparisons should present premium alone without flagging term differences or exception-based quote status — direct extension of Quote Comparison's zero-misleading-comparison gate
- **Remarket value validation:** demonstrate, over the first full renewal cycle post-launch, that RR-08's suppression logic (NO_REMARKET on low-historical-value accounts) doesn't correlate with missed savings — this is a slower-to-validate metric than the others, since it requires a full cycle of data, but should be tracked from day one

---

## 3. Users & Personas

| Persona | Role in this workflow |
|---|---|
| **Wholesale Broker / Production Underwriter** (primary user) | Reviews remarket recommendation, initiates remarketing when appropriate, makes final renewal/carrier decision |
| **Brokerage Principal / Managing Partner** (secondary) | Cares about renewal retention economics — both the cost of over-remarketing (wasted effort, strained carrier relationships) and the risk of under-remarketing (missed savings, missed non-renewal signals) |
| **Incumbent Carrier Underwriting Team** (indirect, external party) | Sends renewal terms (or doesn't) — their responsiveness is itself a data input to this workflow, not just their stated terms |
| **Retail Agent** (indirect, downstream) | Ultimately receives renewal outcome communication via the Retail Agent Communication Copilot, consistent with every prior workflow's downstream integration pattern |

---

## 4. End-to-End Workflow

```
1. A bound policy approaches renewal (triggered by a renewal reminder
   window, similar architecturally to the MGA Renewal Trigger Service
   and this vertical's other scheduled-monitoring processes)
2. System retrieves the bound policy record (from Binder & Policy
   Issuance Coordination) and any mid-term endorsement history (from
   Endorsement Processing) to establish the current, accurate account
   profile — not just the original bind terms
3. System runs exposure change detection (RR-01) and loss history
   change detection (RR-02) against this current profile
4. System checks incumbent appetite (RR-03) and monitors for renewal
   terms arrival; if terms don't arrive within a configured window
   despite broker follow-up, RR-07 flags silent non-response
5. System determines the remarket trigger level (RR-04): NO_REMARKET,
   LIGHT_REMARKET_CHECK, FULL_REMARKET, or URGENT_REMARKET — weighing
   RR-01/02/03/07's signals together with RR-08's relationship-cost/
   history context
6. Broker reviews the recommendation:
   a. NO_REMARKET: broker reviews incumbent terms and accepts (outside
      this workflow's own scope to auto-accept, per Section 2.2)
   b. LIGHT_REMARKET_CHECK or FULL_REMARKET: broker approves initiating
      a remarket, which re-invokes Market Matching (RR-05) against the
      account's current profile
   c. URGENT_REMARKET: broker is alerted with elevated priority and
      initiates remarketing immediately, in parallel with continued
      incumbent follow-up
7. If remarketed, any resulting alternative quotes are compared against
   the incumbent's renewal offer (RR-06), reusing Quote Comparison's
   comparability discipline, with exception-based quotes explicitly
   flagged
8. Broker makes the final renewal decision (stay with incumbent, switch
   carriers) — outside this workflow's authority to make automatically
9. System logs the full decision trail — trigger level, remarket
   outcome if executed, final decision — both for the Feedback/Eval
   Store and specifically to build the remarketing-history data that
   RR-08 depends on for future cycles (this workflow is, notably, the
   first in the vertical whose own output directly improves its future
   accuracy through this history mechanism, distinct from the
   deliberately-deferred Carrier Appetite Intelligence workflow)
```

**Design principle:** this workflow's central contribution isn't a new
kind of judgment — it's correctly routing three different judgment
situations (pricing/severity-driven, opportunity-driven, and
lapse-risk-driven) to three different levels of broker effort and
urgency, rather than treating "should we remarket" as a single yes/no
question. Getting that routing right is worth more than any individual
rule's precision.

---

## 5. Functional Requirements

### 5.1 Renewal Triggering & Data Retrieval

- **FR-1:** Generate a renewal review entry on a configurable pre-expiration schedule (default: 90 days out, consistent with the MGA Renewal Management PRD's window), reading the expiration date from the bound policy record.
- **FR-2:** Retrieve the current, accurate account profile by combining the original bind record (Binder & Policy Issuance Coordination) with any subsequent endorsement history (Endorsement Processing) — per Scenario 03's pattern, exposure changes already reflected in an endorsement must not be re-treated as new information at renewal.

### 5.2 Change Detection

- **FR-3:** Port the exposure change detection logic from the MGA Renewal Management PRD's RN-01 through RN-05 (revenue/headcount/state/operations change), adapted to read from the wholesale bound-policy data source per FR-2.
- **FR-4:** Port the loss history change detection logic from RN-06 through RN-08 (new claims, favorable resolution, frequency trend break), same adaptation.

### 5.3 Incumbent Appetite & Responsiveness

- **FR-5:** Check the incumbent carrier's current Carrier Appetite Profile (reused from Market Matching) against the account's current profile — has anything about the carrier's stated appetite changed since binding, independent of whether they've responded with renewal terms.
- **FR-6:** Track incumbent responsiveness distinctly from stated appetite (per RR-03/RR-07's interpretation note) — monitor for renewal terms arrival against a configurable pre-expiration threshold, and flag non-response as its own signal, not merged into the appetite check.

### 5.4 Remarket Trigger Decision

- **FR-7:** Implement the four-state trigger output (`NO_REMARKET` / `LIGHT_REMARKET_CHECK` / `FULL_REMARKET` / `URGENT_REMARKET`) per RR-04 — this must not be collapsed into a binary decision at any point in the implementation, including in the review UI, since Scenario 03's light-check state is a distinct, valuable output the binary version would lose.
- **FR-8:** `URGENT_REMARKET` (driven by RR-07's non-response detection) must be visually and positionally distinct from the other three states in the broker's review queue, consistent with the urgency-separation pattern established across every Coverline workflow — this is a lapse-risk alert, not a routine renewal review item.
- **FR-9:** The trigger decision's reasoning must explicitly cite which signal(s) drove it (adverse pricing, favorable opportunity, non-response, or historical low-value) — a broker should never see a trigger level without understanding why, consistent with the grounding/citation standard established throughout this project.

### 5.5 Relationship Cost / History Weighting

- **FR-10:** Maintain a per-account remarketing history (prior cycles' trigger level, whether remarketed, outcome/savings if any) as part of the bound policy record, and factor this into the RR-04 decision per RR-08 — an account with a demonstrated pattern of low-value remarketing should weight toward NO_REMARKET even absent other signals, but this weighting must be traceable to that account's actual history, not a generic size- or class-based assumption.
- **FR-11:** Where no remarketing history exists yet (first renewal cycle for this account), RR-08 must have no suppressive effect — this factor only accumulates value over multiple cycles and should not bias a first-cycle decision.

### 5.6 Remarket Execution & Comparison

- **FR-12:** When a remarket is approved (light or full), re-invoke the existing Submission Market Matching engine directly against the account's current profile — this must be a genuine re-invocation of that existing capability, not a separately-built ranking logic specific to this workflow.
- **FR-13:** Apply Quote Comparison's QC-01 term-normalization discipline to any comparison between the incumbent's renewal offer and remarketed alternatives — never present premium alone without flagging limit/deductible/term differences.
- **FR-14:** Flag when an alternative quote required a manual underwriting exception to the carrier's stated appetite profile (per RR-06's extension of Quote Comparison's logic) — present this context explicitly rather than treating an exception-based quote identically to a standard one.

### 5.7 Human Review Interface

- **FR-15:** Renewal review queue showing: trigger level (with visual distinction for URGENT_REMARKET), reasoning citations, incumbent renewal terms if received, and — once a remarket is executed — the comparison view extending Quote Comparison's existing UI pattern.
- **FR-16:** One-click actions appropriate to each trigger state: Accept incumbent terms (NO_REMARKET) / Approve light check / Approve full remarket / Escalate urgent remarket.
- **FR-17:** All broker decisions and outcomes logged, both for the standard feedback loop and specifically to populate the remarketing-history data feeding future RR-08 evaluations (per FR-10).

### 5.8 Non-Functional Requirements

- **FR-18:** Renewal review generation and change detection: target < 10 minutes processing time, consistent with the MGA Renewal Management PRD's target given the similar underlying comparison logic.
- **FR-19:** The renewal-triggering schedule (FR-1) must run as an ongoing scheduled process, the fourth such process in this vertical (alongside Market Matching's carrier-profile staleness check, Quote Comparison's validity monitor, and Binder & Policy Issuance's policy-issuance/post-bind-obligation monitors) — continue building on shared scheduled-job infrastructure rather than a bespoke implementation.
- **FR-20:** Same data retention, encryption, and access-control requirements as every prior Coverline workflow.

---

## 6. Rule Engine

**See the companion document, `RULE_ENGINE_INTERPRETATION_GUIDE.md`, for
full interpretation notes and worked examples.** Summary:

| Rule ID | Rule | Reuse source |
|---|---|---|
| RR-01 | Exposure Change Detection | Ported from MGA Renewal Management RN-01–05 |
| RR-02 | Loss History Change Detection | Ported from MGA Renewal Management RN-06–08 |
| RR-03 | Incumbent Appetite Recheck | Reuses Market Matching's Carrier Appetite Profile |
| RR-04 | Remarket Trigger Decision | **New — four-state graduated output, the core of this PRD** |
| RR-05 | Remarket Execution | Direct re-invocation of Market Matching |
| RR-06 | Renewal Terms Comparability | Reuses Quote Comparison's QC-01, extended with exception-quote flagging |
| RR-07 | Incumbent Non-Response Detection | New — distinct from RR-03, behavior-based not profile-based |
| RR-08 | Relationship Cost / History Weighting | New — the anti-reflexive-remarketing control |

**All thresholds (the 90-day trigger window, the non-response detection
window, the premium-disproportionality threshold that helps distinguish
Scenario 02 from Scenario 01) are placeholders**, consistent with every
rules document in this project, and must be validated with the design
partner's brokers during discovery.

---

## 7. Data Schemas

### 7.1 Remarket Decision Output Schema

```json
{
  "renewal_review_id": "string",
  "bind_id": "string",
  "named_insured": "string",
  "incumbent_carrier_id": "string",
  "exposure_change": {"fields_changed": ["list"], "material": "boolean", "already_endorsed": "boolean"},
  "loss_history_change": {"new_claims_count": "integer", "favorable_resolutions_count": "integer", "trend": "improving | worsening | flat"},
  "incumbent_status": {
    "renewal_terms_received": "boolean",
    "days_before_expiration_at_receipt": "integer, null if not received",
    "non_response_flag": "boolean"
  },
  "remarketing_history": [
    {"cycle_year": "integer", "trigger_level": "string", "remarketed": "boolean", "savings_identified": "currency, null if none"}
  ],
  "trigger_decision": {
    "level": "NO_REMARKET | LIGHT_REMARKET_CHECK | FULL_REMARKET | URGENT_REMARKET",
    "reasoning": {"summary": "string", "citations": [{"claim": "string", "source": "string"}]}
  },
  "remarket_execution": {
    "initiated": "boolean",
    "market_matching_output_id": "string, null if not remarketed",
    "comparison_output": "object, reuses Quote Comparison PRD Section 7.2 schema"
  },
  "final_decision": {"outcome": "renewed_incumbent | switched_carrier | pending", "decided_by": "string", "timestamp": "datetime"}
}
```

---

## 8. System Architecture (Level 2)

```
┌───────────────────────────┐
│ Renewal Trigger Service         │  (new instance of the scheduled-
│ (90-day pre-expiration window)  │   monitoring pattern used elsewhere
└────────────┬─────────────────┘  │   in this vertical)
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Account Profile Assembly        │◄─────┤ Bound Policy Record            │
│ (bind + endorsement history)    │      │ (Binder & Policy Issuance) +   │
└────────────┬─────────────────┘      │ Endorsement History             │
             ▼                          │ (Endorsement Processing)        │
┌───────────────────────────┐      └───────────────────────────┘
│ Change Detection Engine          │  (RR-01/RR-02, ported from MGA
│                                   │   Renewal Management)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Incumbent Appetite &             │◄─────┤ Carrier Appetite Profile DB    │
│ Responsiveness Check             │      │ (existing, Market Matching)    │
│ (RR-03, RR-07)                   │      └───────────────────────────┘
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Remarket Trigger Decision        │◄─────┤ Remarketing History Store      │
│ Engine (RR-04 — four-state,      │      │ (new — per-account, feeds      │
│  RR-08 weighting)                │      │  RR-08 across cycles)          │
└────────────┬─────────────────┘      └───────────────────────────┘
             │
             ├──── NO_REMARKET ──────► Broker reviews incumbent terms
             │
             └──── LIGHT / FULL / URGENT
                          ▼
             ┌───────────────────────────┐
             │ Market Matching Engine          │  (EXISTING — direct
             │ (re-invoked, RR-05)              │   re-invocation, no new
             └────────────┬─────────────────┘  │   ranking logic)
                          ▼
             ┌───────────────────────────┐
             │ Comparison Engine (RR-06)       │  (extends Quote Comparison's
             │                                  │   QC-01 discipline)
             └────────────┬─────────────────┘
                          ▼
             ┌───────────────────────────┐
             │ Broker Review & Final Decision  │◄──── Logged to Remarketing
             └───────────────────────────────┘        History Store (FR-17)
```

**Key architectural point:** this workflow is best understood as an
**orchestration layer**, not a new capability — RR-05 explicitly
re-invokes Market Matching rather than reimplementing ranking, RR-06
explicitly reuses Quote Comparison's comparability logic, and RR-01/02
are direct ports from the MGA vertical's Renewal Management PRD. The
genuinely new engineering is concentrated in RR-04 (the four-state
trigger decision) and RR-08 (the history-weighting mechanism) — budget
accordingly, and treat the rest of this build as integration work
against already-proven components.

---

## 9. Risks & Open Questions

| Risk | Mitigation / Owner |
|---|---|
| RR-04's four-state trigger decision is the most subjective judgment call in this PRD, and thresholds distinguishing (for example) Scenario 02's FULL_REMARKET from Scenario 03's LIGHT_REMARKET_CHECK are placeholders based on illustrative reasoning, not real broker judgment | Validate extensively with the design partner's brokers during discovery — this is the rule most likely to need real calibration adjustment after initial deployment, more so than any binary threshold elsewhere in this vertical |
| RR-08's relationship-cost weighting depends on accumulated remarketing history that won't exist for any account in the first renewal cycle post-launch | Set expectations that RR-08 provides no value in year one and grows in usefulness over subsequent cycles — don't treat its absence of effect early on as a sign the rule isn't working |
| RR-07's non-response detection threshold needs to balance "enough time for the incumbent to reasonably respond" against "enough time remaining to complete a remarket if needed" — get this wrong in either direction and it either false-alarms on normal carrier turnaround times or triggers too late to be useful | Validate against real incumbent carrier response-time patterns during discovery, and treat this threshold as carrier-specific if data supports it, not a single vertical-wide default |
| This workflow depends on accurate endorsement history being available (FR-2) — if Endorsement Processing wasn't fully adopted or has gaps in its logged history, exposure change detection could incorrectly treat already-known changes as new signals (the exact failure mode Scenario 03 is built to avoid) | Confirm Endorsement Processing's logging completeness for any account entering this workflow before trusting RR-01's "already endorsed" distinction; flag data gaps rather than assuming completeness |

---

## 10. Rollout Plan

1. **Discovery (2 weeks):** validate RR-04's four-state thresholds and RR-07's non-response window with real brokers, confirm exposure/loss-change detection thresholds ported from the MGA PRD still make sense for this vertical's typical account profiles.
2. **Build v0 (3-4 weeks — lighter than Quote Comparison or Binder & Policy Issuance, given how much of this workflow orchestrates existing components rather than building new ones):** Renewal Trigger Service, Account Profile Assembly, Change Detection Engine (ported), Incumbent Appetite/Responsiveness Check, Remarket Trigger Decision Engine, Remarketing History Store, integration calls to Market Matching and Quote Comparison's comparison logic.
3. **Shadow mode (2-3 weeks, ideally spanning at least a partial real renewal cycle):** run against real approaching renewals in parallel with brokers' normal process.
4. **Live pilot (4 weeks minimum, ideally longer given renewal cycles are inherently slower-paced than the other workflows in this vertical):** system output enters the real review queue, Section 2.3 metrics tracked, with URGENT_REMARKET's zero-missed-trigger gate treated as non-negotiable throughout.
5. **Go/no-go review:** against Section 2.3 criteria — at this point, all six workflows gated on "needs real bound-policy/renewal data" will have been built (Market Matching, Package Assembly, Retail Agent Communication, Binder & Policy Issuance, Endorsement Processing, Renewal Remarketing), leaving only the three deliberately-deferred or lower-priority items (Diligent Search automation, Carrier Appetite Intelligence, Pipeline & Carrier Performance Reporting) from the original 10-workflow roadmap.

---

*This document defines v1 scope only. Automated remarket execution, automated incumbent-term acceptance, predictive appetite-exit modeling, and multi-policy renewal coordination should be treated as new PRD scope. Given that this PRD completes the full bind-to-renewal lifecycle for the Wholesale/E&S vertical, the next real decision point is not "which workflow next" but "is it time to validate everything built so far with an actual design partner before continuing" — a question this document does not answer and should not attempt to.*
