# PRD: Carrier Appetite Intelligence Tracking Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Draft for engineering scoping — read this PRD's Section 2
before any other section
**Owner:** [Product]
**Last updated:** 2026-07-16
**Depends on:** Signal data already logged (but not acted on) by Quote Comparison's QC-03 and Renewal Remarketing's remarketing-history mechanism, plus the Carrier Appetite Profile schema from Market Matching.

---

## 0. Read this before anything else in this document

This workflow has been explicitly flagged as the highest scope-creep
risk in the entire Wholesale/E&S vertical at every prior mention:

- Market Matching's Section 2.2: *"a full 'living appetite intelligence'
  system is a genuinely hard, ongoing data problem — treat it as a v2+
  capability... Don't let v1 scope quietly expand to chase it."*
- Quote Comparison's QC-03: *"v1 only logs this distinction — it does
  not act on it."*
- Renewal Remarketing's Section 2.2: *"informational logging only in
  v1, feeding the same deferred Carrier Appetite Intelligence workflow
  referenced throughout this vertical's other PRDs."*

This PRD exists because the logged signal data has now accumulated
across three workflows and doing something with it is reasonable — but
**the correct v1 scope is much smaller than the name "Carrier Appetite
Intelligence" suggests.** If anything in this document is read as
license to build an ambitious, autonomous learning system, that is a
misreading. The intended v1 is: aggregate existing signals, flag
genuinely evidenced patterns for human review, and update exactly two
metadata fields automatically. Nothing else.

---

## 1. Problem Statement

Across Market Matching, Quote Comparison, and Renewal Remarketing, Coverline has been logging (but never acting on) real signals about whether carriers' actual behavior matches their stated appetite profiles — declinations that confirm or contradict stated class acceptance, remarketing outcomes, bind confirmation discrepancies. This data currently sits unused. Left entirely unused indefinitely, the Carrier Appetite Profiles that every other workflow in this vertical depends on will slowly drift out of date, since they were established as manually-maintained data with no feedback mechanism (per Market Matching's FR-4 staleness warning).

**Goal of v1:** Aggregate existing logged signals, distinguish genuine class-level appetite-shift patterns from normal account-specific variance, and surface a small number of well-evidenced suggestions for human review — while never automatically modifying substantive appetite data.

**Explicitly not the goal of v1:** Autonomous profile editing of any kind, predictive appetite modeling, real-time appetite tracking, or any capability beyond what's described in Section 2.1.

---

## 2. Scope of v1

### 2.1 In scope (and this is genuinely all of it)
- Aggregating declination-consistency and outcome signals already logged elsewhere (CI-01)
- Distinguishing class-level appetite-shift signals from account-specific decline reasons (CI-02)
- Automatically refreshing exactly two metadata fields — `appetite_confidence` and `appetite_last_updated` — when outcomes consistently confirm a profile (CI-03)
- Generating human-reviewed suggestions when a sufficiently-evidenced inconsistency pattern is found (CI-04)
- Suppressing output by default when signal volume or consistency is insufficient (CI-05)

### 2.2 Explicitly out of scope for v1
- Any automatic modification of `class_codes_accepted`, `class_codes_excluded`, `premium_band`, `severity_ceiling`, or any other substantive Carrier Appetite Profile field — permanently, not just in v1
- Predictive modeling of future appetite shifts
- Real-time or continuous monitoring beyond periodic batch aggregation of already-logged signals
- New signal collection mechanisms — this workflow only consumes what other workflows already log
- Any autonomous action beyond the two-field metadata refresh described in CI-03

### 2.3 Success criteria (must hit before expanding scope)
- **Suppression rate as a primary health metric, not just an accuracy metric:** the large majority of carrier/class evaluations should produce no output — track this rate explicitly, and treat an unexpectedly low suppression rate as a bug to investigate, not a sign of a more capable system
- **Zero account-specific signals mis-scored as class-level patterns:** 0% in the pre-launch eval, given how directly this determines whether the workflow produces useful signal or constant noise
- **Zero unauthorized substantive profile changes:** 0 instances, ever, of `class_codes_accepted`/`excluded` or other substantive fields changing without explicit human approval — architectural gate, not a tunable target

---

## 3. Users & Personas

| Persona | Role |
|---|---|
| **Wholesale Broker / Underwriting Manager** (primary user, reviewer of suggestions) | Reviews and approves or dismisses suggested profile changes |
| **Brokerage Principal** (secondary) | Cares about Carrier Appetite Profile data staying current without manual audit effort |

---

## 4. End-to-End Workflow

```
1. Periodic batch job (not real-time) aggregates signals logged by
   Quote Comparison (QC-03) and Renewal Remarketing (RR-08 history)
   since the last run
2. For each carrier/class combination with new signals, CI-02 scores
   consistency, explicitly distinguishing class-level stated reasons
   from account-specific ones
3. CI-05 suppression check: is there sufficient volume and consistency
   to justify any output? (Expected: no, for most combinations)
4. If fully consistent: CI-03 refreshes appetite_confidence/
   appetite_last_updated automatically — no human step needed for this
   narrow metadata update
5. If a genuine inconsistency pattern is found: CI-04 generates a
   suggestion, placed in a review queue, with the specific evidence
   cited
6. Broker/underwriting manager reviews the suggestion and either
   approves the profile change (manually, via the existing Carrier
   Appetite Profile management interface from Market Matching — this
   workflow does not introduce a new editing surface) or dismisses it
7. All suggestions and their resolutions are logged
```

---

## 5. Functional Requirements

- **FR-1:** Run as a periodic batch process (not real-time or event-triggered), consuming only signals already logged by other workflows.
- **FR-2:** Score consistency separately for outcomes with class-level stated reasons versus account-specific stated reasons (per CI-02) — never combine these into a single consistency score.
- **FR-3:** Require a minimum signal volume and recency threshold (configurable, validated during discovery) before generating any suggestion — default to suppression.
- **FR-4:** Automatically update only `appetite_confidence` and `appetite_last_updated` fields, and only when signals are consistently confirming — this must be enforced architecturally (the write path for this workflow should have no code route capable of modifying any other field), not just as a policy convention.
- **FR-5:** Suggestions must cite the specific evidence (which submissions, which outcomes, which stated reasons) driving them, consistent with the grounding standard across every Coverline workflow.
- **FR-6:** Suggestion review and approval reuses the existing Carrier Appetite Profile management interface from Market Matching rather than introducing a parallel editing surface.

---

## 6. Rule Engine

**See the companion `RULE_ENGINE_INTERPRETATION_GUIDE.md`.** Summary:
CI-01 (aggregation only), CI-02 (class-level vs. account-specific
distinction — the rule most likely to be built wrong), CI-03 (the only
automatic write path, narrowly scoped to two metadata fields), CI-04
(human-reviewed suggestions only), CI-05 (suppression is the default
and expected outcome).

---

## 7. Data Schema

```json
{
  "suggestion_id": "string",
  "carrier_id": "string",
  "class_code": "string",
  "evidence": [{"submission_id": "string", "outcome": "string", "date": "date", "stated_reason": "string", "reason_scope": "class_level | account_specific"}],
  "pattern_type": "CONFIRMED_CONSISTENT | GENUINE_INCONSISTENCY | INSUFFICIENT_SIGNAL",
  "suggested_action": "string, null unless GENUINE_INCONSISTENCY",
  "status": "SUPPRESSED | METADATA_AUTO_UPDATED | PENDING_REVIEW | APPROVED | DISMISSED"
}
```

---

## 8. Risks & Open Questions

| Risk | Mitigation |
|---|---|
| The single biggest risk to this PRD is scope creep beyond what Section 2.1 describes — every prior PRD in this vertical warned about this workflow specifically | Treat Section 0 and 2.1 as binding; any proposal to expand this workflow's scope should be treated as a new PRD requiring the same deliberate reconsideration flagged throughout this vertical, not an incremental addition |
| Signal volume may be genuinely low for months after launch, since it depends on other workflows having accumulated real usage history | Set expectations that this workflow may produce near-zero output initially — that's correct behavior, not underperformance |
| CI-02's class-level vs. account-specific distinction depends on carrier decline reasons being captured with enough detail by upstream workflows (QC-03) | Confirm QC-03's actual logged data includes enough reason detail to support this distinction; if not, this workflow may need to wait for upstream logging improvements rather than guessing at the distinction from incomplete data |

---

## 9. Rollout Plan

1. **Discovery (1 week):** confirm signal volume/quality actually available from QC-03 and Renewal Remarketing logs; set suppression thresholds with real underwriters.
2. **Build v0 (2 weeks — small, given this is aggregation plus a narrow write path, not new capability):** batch aggregation job, CI-02 scoring, CI-05 suppression, CI-03's tightly-scoped auto-update, CI-04 suggestion generation into the existing review interface.
3. **Shadow mode (2-3 weeks, ideally longer given low expected signal volume):** run and observe suppression rate and suggestion quality before any suggestions are surfaced live.
4. **Live pilot:** suggestions enter the real review queue; Section 2.3's suppression-rate health metric tracked from day one.

---

*This document defines v1 scope only, and per Section 0, that scope is intentionally narrow. Any expansion — predictive modeling, real-time monitoring, autonomous editing of substantive profile fields — requires a new PRD and a fresh, deliberate decision, not an assumed natural next step.*
