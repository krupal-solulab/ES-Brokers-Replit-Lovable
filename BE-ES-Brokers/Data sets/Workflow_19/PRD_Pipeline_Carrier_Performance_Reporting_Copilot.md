# PRD: Pipeline & Carrier Performance Reporting Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Draft for engineering scoping
**Owner:** [Product]
**Last updated:** 2026-07-16
**Depends on:** Aggregated logs from all six prior wholesale workflows (Market Matching, Package Assembly, Retail Agent Communication, Quote Comparison, Binder & Policy Issuance, Endorsement Processing, Renewal Remarketing). This is a pure aggregation/reporting layer — the last workflow on the original 10-item roadmap, appropriately sequenced last since it has nothing meaningful to report on until the others are producing real data.

---

## 1. Problem Statement

A brokerage principal or managing partner has no easy way to see the health of the placement pipeline across submissions, carrier relationships, and renewals without manually pulling data from each workflow separately. Once six other workflows are logging real activity, there's genuine value in a rollup view — but that value depends entirely on the report being honest about what it actually knows. A pipeline report is only as trustworthy as its handling of the two failure modes that have shown up repeatedly throughout this project: presenting a low-confidence number with false precision, and smoothing over missing data to produce a cleaner-looking chart.

**Goal of v1:** Aggregate existing workflow logs into a pipeline funnel view, carrier hit-rate comparisons, time-to-placement metrics, and remarketing value reporting — with explicit, non-negotiable handling of low-volume figures and data gaps.

**Explicitly not the goal of v1:** Predictive forecasting, automated goal-setting or alerting based on performance thresholds, or any new data collection beyond aggregating what other workflows already log.

---

## 2. Scope of v1

### 2.1 In scope
- Pipeline funnel reporting across all major stages (PR-01)
- Carrier hit-rate comparison with mandatory low-volume annotation (PR-02)
- Time-to-placement metrics, correctly excluding broker/agent-side delay from carrier-attributed timing (PR-03)
- Revenue attribution by carrier relationship (PR-04) — flagged for discovery-phase validation given brokerage-specific commission structures
- Remarketing value reporting, distinguishing savings-identified from confirmation-value outcomes (PR-05)
- Explicit, mandatory data-completeness flagging for any gap in underlying logs (PR-06)

### 2.2 Explicitly out of scope for v1
- Predictive/forecasting capability of any kind
- Automated performance-threshold alerting (e.g., "carrier X's hit rate dropped below Y%, notify management") — this is a reasonable future extension but introduces a new judgment layer (what threshold matters, to whom) that deserves its own deliberate scoping
- Any new data collection — this workflow strictly aggregates existing logs
- Broker-level individual performance scorecarding — flagged as a sensitive HR-adjacent extension that deserves separate, deliberate product and possibly legal consideration, not a default inclusion in a v1 pipeline report

### 2.3 Success criteria (must hit before expanding scope)
- **Zero silently-smoothed data gaps:** 0% of reports in the pre-launch eval should present a period with known logging gaps as if the data were complete — hard gate, the direct throughline from this entire project's first critique (the original landing page's fabricated stats)
- **Zero unannotated low-volume figures:** 100% of rate/percentage metrics below a configurable volume threshold must carry an explicit low-confidence annotation
- **Remarketing value framing accuracy:** 100% of remarket outcomes in the eval set must be categorized as either savings-identified or confirmation-value, never collapsed into a single ambiguous "outcome" figure that could misrepresent a good decision as a null result

---

## 3. Users & Personas

| Persona | Role |
|---|---|
| **Brokerage Principal / Managing Partner** (primary user) | Reviews pipeline health, carrier relationship performance, remarketing value |
| **Wholesale Broker** (secondary) | May reference personal or account-level activity, though individual scorecarding is explicitly out of scope per Section 2.2 |

---

## 4. End-to-End Workflow

```
1. Scheduled or on-demand report generation pulls logs from all six
   prior workflows for the requested period
2. System checks data completeness per source workflow/stage (PR-06) —
   any identified gap is flagged before any calculation proceeds
3. Funnel metrics computed (PR-01), carrier hit-rates computed with
   volume-based annotation (PR-02), time-to-placement computed with
   broker/agent-delay exclusion (PR-03), revenue attributed (PR-04),
   remarketing value categorized (PR-05)
4. Report presented to the principal/broker, with completeness status
   and any annotations prominently displayed, not buried in footnotes
```

---

## 5. Functional Requirements

- **FR-1:** Aggregate stage-level counts directly from each source workflow's own logged events (Market Matching, Package Assembly, Quote Comparison, Binder & Policy Issuance) — no independent tracking mechanism.
- **FR-2:** Check and flag data completeness per stage and period before computing any dependent metric; a report covering a period with a known gap must display that gap explicitly, never interpolate or omit it silently.
- **FR-3:** Any rate/percentage metric must display alongside its underlying volume (denominator), and must carry an explicit annotation when volume falls below a configurable threshold.
- **FR-4:** Time-to-placement calculations must exclude periods attributable to broker/retail-agent-side delay (e.g., time a submission spent in Package Assembly's BLOCKED status) from carrier-attributed timing metrics.
- **FR-5:** Remarketing value reporting must categorize each remarketed account's outcome as either a quantified savings figure or a qualitative confirmation-value outcome — never a single merged metric that could misrepresent one as the other.
- **FR-6:** Revenue attribution logic must be validated against the design partner's actual commission structure during discovery before being treated as reliable — flag as provisional until confirmed.

---

## 6. Rule Engine

**See the companion `RULE_ENGINE_INTERPRETATION_GUIDE.md`.** Summary:
PR-01 (stage definitions), PR-02 (low-volume annotation — mandatory),
PR-03 (delay attribution correctness), PR-04 (revenue, needs discovery
validation), PR-05 (remarketing value framing), PR-06 (data
completeness — the most important rule in this PRD, direct throughline
to this project's original landing page critique).

---

## 7. Data Schema

```json
{
  "report_id": "string",
  "period": "string",
  "data_completeness": {"status": "COMPLETE | PARTIAL", "gaps": [{"stage": "string", "date_range": "string", "reason": "string"}]},
  "funnel": [{"stage": "string", "count": "integer", "pct_of_prior_stage": "float"}],
  "carrier_performance": [
    {"carrier_name": "string", "submissions_approached": "integer", "quote_rate": "float", "bind_rate": "float", "low_volume_flag": "boolean"}
  ],
  "remarketing_value": [
    {"account": "string", "trigger_level": "string", "outcome_type": "savings_identified | confirmation_value", "savings_amount": "currency, null if confirmation_value"}
  ]
}
```

---

## 8. Risks & Open Questions

| Risk | Mitigation |
|---|---|
| This workflow's credibility depends entirely on disciplined data-completeness handling — the same failure mode flagged in the very first landing page review of this entire project | Treat PR-06 as this PRD's equivalent of every other workflow's highest-stakes gate; a single instance of a smoothed-over gap making it to a principal's report would undermine trust in every other number the system produces |
| Revenue attribution (PR-04) is the one rule not exercised by the sample dataset and depends entirely on brokerage-specific commission structure | Do not build this rule from assumption — treat as a discovery-phase requirement with real financial data from the design partner |
| Low-volume threshold (PR-02) is illustrative in the sample dataset, not validated | Confirm a sensible threshold with the design partner — what counts as "too few submissions to trust a percentage" will vary by their typical carrier panel size |

---

## 9. Rollout Plan

1. **Discovery (1-2 weeks):** confirm revenue/commission structure for PR-04, validate low-volume thresholds, confirm which stakeholders need which views (principal-level vs. broker-level, noting Section 2.2's exclusion of individual scorecarding).
2. **Build v0 (2-3 weeks — pure aggregation, no new extraction or judgment logic beyond the completeness/annotation rules):** aggregation layer, funnel/hit-rate/timing calculations, completeness checking, remarketing value categorization, report UI.
3. **Validation:** run against real accumulated data from the other six workflows once they have sufficient live history — this workflow cannot be meaningfully tested until then, consistent with its position as the last-sequenced item on the original roadmap.

---

*This document defines v1 scope only. Predictive forecasting, automated threshold alerting, and individual broker performance scorecarding should be treated as new PRD scope requiring their own deliberate consideration — the last of these in particular deserves a product and likely HR/legal conversation before being built at all.*
