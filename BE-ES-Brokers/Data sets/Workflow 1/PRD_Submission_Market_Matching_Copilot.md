# PRD: Submission Market Matching Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Live (v1 implemented) — this document was written after the fact to
close a documentation gap; it describes the system as actually built
(`verticals/es/workflows/market_matching/`, `verticals/es/decision_core/matching.py`
and `carrier_profiles.py`), not a forward-looking proposal.
**Owner:** [Product]
**Last updated:** 2026-08-04
**Depends on:** None — this is the first workflow in the Wholesale/E&S Broker
vertical. Every downstream E&S workflow (Package Assembly, Quote Comparison,
Binder & Issuance, etc.) consumes this workflow's carrier-panel data and/or its
matching output as an input, per each of those PRDs' own "Depends on" line.

---

## 1. Problem Statement

A wholesale broker receiving a new submission from a retail agent has to decide
which carrier(s) on their panel to approach — a decision that today depends on
the broker's own memory of dozens of carriers' shifting appetite (class
codes accepted/excluded, licensed states, premium bands, severity tolerance,
document requirements) plus whatever informal notes exist about which
carriers have historically been fast/slow or likely/unlikely to quote a given
class. Getting this wrong costs real time and real carrier goodwill in both
directions: approaching a carrier clearly outside its appetite wastes that
underwriter's attention and mildly damages the relationship, while missing a
carrier that *would* have fit means a slower, more expensive placement than
necessary. Wholesale brokers are also the last line of defense on a
compliance obligation most of them treat as an afterthought: many states
require documented evidence that admitted markets were shopped and declined
before E&S placement is permitted, and that diligent-search paperwork still
has to exist even when — especially when — no carrier on the panel is a fit.

**Goal of v1:** Given an extracted submission (class code, states of
operation, indicated premium, loss run), rank every carrier on the current
panel that is a genuine appetite fit, correctly and completely exclude every
carrier that is not, surface per-carrier missing-information gaps without
letting them suppress an otherwise-good match, and independently determine
whether diligent-search compliance documentation is required and on file —
including, and especially, in the true zero-match case.

**Explicitly not the goal of v1:** Assembling or sending anything to a
carrier (that begins in Package Assembly), generating diligent-search
documentation itself (only flagging whether it's on file — see Section 2.2),
or learning/adjusting carrier appetite data over time from placement outcomes
(that's the deferred Carrier Appetite Intelligence workflow's job, which this
workflow's logged data is intended to eventually feed).

---

## 2. Scope of v1

### 2.1 In scope
- Baseline submission validation (is there even an ACORD application to read a
  class code / indicated premium from) before matching runs at all
- Hard-exclusion checks against every carrier on the panel: class-code fit
  (scope-aware, not keyword matching), state licensing, premium band, explicit
  class exclusion list (Section 6, MM-01/02/03/04)
- Soft-scoring/ranking for every carrier that survives hard exclusion:
  class-fit specificity, submission completeness, historical hit rate,
  appetite-confidence weighting, severity margin (Section 6, MM-05/06)
- Per-carrier missing-information flags that adjust rank without excluding a
  carrier outright (the completeness-vs-exclusion distinction that is this
  workflow's single most important design decision — see the companion
  `RULE_ENGINE_INTERPRETATION_GUIDE.md`)
- Independent diligent-search compliance check (MM-07) that runs on every
  submission regardless of ranking outcome, including true zero-match
- Explicit "no market found on current panel" output when zero carriers
  survive hard exclusion — never a forced best-available recommendation
- A fixed, JSON-file-backed carrier appetite panel per dataset
  (`carrier_profiles/*.json`), loaded per request

### 2.2 Explicitly out of scope for v1
- Any package assembly, document generation, or carrier-facing communication
  (Package Assembly Copilot's job, which this workflow's output feeds
  directly, per that PRD's Section 4)
- Generating diligent-search documentation from scratch — v1 only checks
  whether a documented declination count is present in the extracted
  submission data and reports how many more are needed for a complete record;
  it does not draft, request, or fabricate that documentation
- Carrier appetite data maintenance/ingestion tooling — v1 reads a static
  per-dataset JSON panel; keeping that panel current against real carriers'
  actual, changing appetite is a real ongoing operational cost not solved by
  this PRD (see Section 9)
- Learning or adjusting scoring weights/appetite data from historical
  placement outcomes — the ranking formula's weights (Section 6) are fixed
  placeholders in v1, not a model that improves with use

### 2.3 Success criteria (must hit before expanding scope)
- **Zero false-inclusions:** 0% of carriers appearing in a ranked output in
  the pre-launch eval should actually fail a hard-exclusion rule (MM-01/02/
  03/04) — a carrier shown to a broker as viable that isn't wastes exactly
  the relationship-trust this workflow exists to protect.
- **Zero forced matches:** 100% of true zero-match submissions in the
  pre-launch eval (every carrier hard-excluded) must produce an explicit
  no-market result with the diligent-search flag still evaluated — never an
  error, and never a "best available" recommendation on an excluded class.
- **Completeness-vs-exclusion correctness:** carriers with a genuine
  appetite fit but an incomplete document/loss-run package must still appear
  in the ranked output with a specific missing-item note, not be filtered out
  — measured directly against the sample dataset's Submission 01 case, which
  exists specifically to catch this failure mode.
- **Time saved per submission:** reduce broker time spent manually screening
  the panel by a meaningful, discovery-validated margin (no baseline number
  fixed yet — placeholder pending real broker time-tracking, consistent with
  every other workflow's unset targets in this vertical).

---

## 3. Users & Personas

| Persona | Role in this workflow |
|---|---|
| **Wholesale Broker / Production Underwriter** (primary user) | Reviews the ranked carrier shortlist and exclusion reasons, selects which carrier(s) to approach, hands that selection to Package Assembly |
| **Brokerage Principal / Managing Partner** (secondary, buyer) | Cares about placement speed and about the brokerage never damaging a carrier relationship with an obviously-wrong approach |
| **Carrier Underwriter** (indirect, non-user) | Never sees this workflow's output directly, but is the actual reason exclusion correctness matters — an underwriter who receives submissions outside their own stated appetite loses trust in the broker sending them |

---

## 4. End-to-End Workflow

```
1. A submission arrives (ingested the same way as every other E&S workflow —
   connector -> RawBundle -> extraction) and is handed to Market Matching as
   the FIRST workflow in the vertical to touch it
2. Baseline validation runs: is there an ACORD application present with a
   readable class code and indicated premium? If not, the workflow stops here
   with REQUEST_INFO — carrier matching cannot run without it
3. The current carrier panel is loaded (a fixed set of carrier appetite
   profiles for this dataset/tenant)
4. EVERY carrier on the panel is evaluated independently against the
   submission's extracted data:
   a. MM-04 (explicit exclusion list) and MM-01 (scoped class-code accept)
      checked first — hard exclusion, carrier does not appear in output at all
   b. MM-02 (state licensing) checked — hard exclusion if any operating
      state is unlicensed
   c. MM-03 (premium band) checked — hard exclusion outside the band, with a
      near-edge informational flag inside a 10% threshold
   d. For carriers surviving a-c: MM-05 (severity ceiling — hard for classes
      where that's a firm appetite boundary, e.g. roofing; a soft scoring
      factor otherwise) and MM-06 (document/loss-run completeness) are
      evaluated and folded into a weighted composite score
5. MM-07 (diligent-search compliance) runs independently of steps 4a-d,
   including when zero carriers survive — this is not conditional on a match
   existing
6. Surviving carriers are ranked by composite score; a broker sees the full
   ranked list, each carrier's missing-item flags (if any), the full list of
   hard-excluded carriers with the specific rule and reason each was
   excluded, and the diligent-search compliance note
7. Broker selects one or more carriers to approach — this selection is the
   direct trigger/input for the Package Assembly Copilot (see that PRD's
   Section 4, step 1)
```

---

## 5. Functional Requirements

### 5.1 Input Validation
- **FR-1:** Before matching runs, validate that the submission has a readable
  ACORD application (class code, indicated premium). If missing, return
  `REQUEST_INFO` with a rationale — do not attempt to match against a panel
  with no class code or premium to check against.

### 5.2 Hard Exclusion
- **FR-2:** Every carrier on the panel is checked against MM-04 (explicit
  class exclusion, checked first — exclusions win on any data conflict with
  an accepted-list entry) and MM-01 (scoped class-code acceptance). A carrier
  failing either never appears in the ranked output, with the specific rule
  and reason recorded in the exclusion list.
- **FR-3:** Class-code matching must be scope-aware, not plain string/keyword
  matching — e.g. "roofing (low slope only)" must not match a submission
  scoped to steep-slope or all-types roofing, per MM-01's interpretation note.
- **FR-4:** State-licensing exclusion (MM-02) checks every state the
  submission operates in; a carrier missing licensing in even one relevant
  state is a hard exclusion for that submission, not a partial match.
- **FR-5:** Premium-band exclusion (MM-03) is a hard exclusion at both the
  floor and ceiling — this is an underwriting appetite boundary, not a soft
  preference, despite the temptation to treat it like the scoring factors
  below. Submissions within 10% of a carrier's band edge get an
  informational note attached instead of (not in addition to) exclusion.

### 5.3 Soft Scoring
- **FR-6:** For every carrier surviving hard exclusion, compute a composite
  score from five weighted factors (Section 6's formula): class-fit
  specificity, submission completeness, historical hit rate, appetite-
  confidence weighting, and severity margin.
- **FR-7:** Severity-ceiling handling (MM-05) is hard for classes where it is
  a genuine firm appetite boundary (v1 implements this as: hard whenever the
  submission's class code contains "roofing", soft — a scoring factor —
  otherwise) and must never be treated as universally hard or universally
  soft across every class.
- **FR-8:** Submission completeness (MM-06) — missing required documents or
  insufficient loss-run years — must reduce a carrier's score and attach a
  specific "missing: [items]" flag, and must NEVER suppress that carrier from
  the ranked output entirely. A carrier that is otherwise a strong appetite
  fit but missing a document must still be visible and ranked on its
  underlying appetite fit — this is the single most important behavior this
  workflow must get right (see the Rule Engine Interpretation Guide's own
  framing of this as the most common implementation mistake).

### 5.4 Diligent Search / Compliance
- **FR-9:** MM-07 (diligent-search documentation check) must run on every
  submission regardless of whether any carrier survives hard exclusion —
  including, and especially, the true zero-match case.
- **FR-10:** The check counts documented admitted-market declinations already
  present in the extracted submission data and reports whether that count
  meets the threshold for a complete record, plus how many more are needed if
  not — it does not generate or request the missing documentation itself
  (that's explicitly out of scope, per 2.2).

### 5.5 Zero-Match Handling
- **FR-11:** When every carrier on the panel is hard-excluded, the system
  must produce an explicit "no market found on current panel" result — never
  an error, and never a forced low-confidence recommendation on an excluded
  class. This is treated as a release-gating eval case (Section 9), not a
  quality nice-to-have, since an incorrect placement recommendation on a
  genuinely excluded class is a worse outcome than accurately reporting no
  market was found.

### 5.6 Output / Review Interface
- **FR-12:** Present, per submission: the ranked list of surviving carriers
  (score, missing-item flags, informational flags), the full list of
  hard-excluded carriers with rule ID and specific reason for each, and the
  diligent-search compliance result — all three sections shown regardless of
  whether the ranked list is empty.
- **FR-13:** Broker's carrier selection from the ranked list is the input
  handoff to Package Assembly — no separate re-entry of submission data
  required downstream.

### 5.7 Non-Functional Requirements
- **FR-14:** Every carrier on the panel is evaluated independently per
  submission — no shared mutable state between carriers that could let one
  carrier's evaluation affect another's result.
- **FR-15:** Same data retention, encryption, and access-control requirements
  as every other Coverline workflow.

---

## 6. Rule Engine

**See the companion document, `RULE_ENGINE_INTERPRETATION_GUIDE.md`, for the
full interpretation notes, worked examples, and the three-tier exclusion/
scoring/informational framing that this rule engine depends on getting
right.** Summary:

| Rule ID | Rule | Type |
|---|---|---|
| MM-01 | Class code match (scoped, not keyword) | Hard exclusion |
| MM-02 | State licensing match (all operating states) | Hard exclusion |
| MM-03 | Premium band fit | Hard exclusion (both ends); informational within 10% of an edge |
| MM-04 | Explicit class exclusion list | Hard exclusion, checked before MM-01, wins on conflict |
| MM-05 | Severity ceiling | Soft scoring factor by default; hard exclusion for classes where the ceiling is a firm appetite boundary (v1: roofing classes) |
| MM-06 | Submission completeness (documents + loss-run years) | Soft scoring + informational — never suppresses a carrier's rank |
| MM-07 | Diligent search / compliance documentation | Independent — runs regardless of ranking outcome, including zero-match |

**Ranking formula** (for carriers surviving MM-01/02/03/04):

```
score = (class_fit_specificity  * 0.30)
      + (completeness_score     * 0.25)   [1.0 minus a per-missing-item deduction]
      + (historical_hit_rate    * 0.25)   [from the carrier profile]
      + (appetite_confidence_weight * 0.10)  [high=1.0, medium=0.6, low=0.3]
      + (severity_margin        * 0.10)   [headroom below the severity ceiling]
```

**These weights are fixed placeholders in v1**, consistent with every other
rules document in this project — they have not been validated against real
wholesale broker priorities, and a broker weighting placement speed
(historical hit-rate) far above class-fit precision, or vice versa, would be
a reasonable adjustment to make during discovery for a real deployment.

**Known simplification vs. the interpretation guide:** the guide suggests
adding a `ceiling_type: hard | soft` field to each carrier's profile so the
MM-05 hard/soft distinction could be configured per carrier/class
combination. v1 does not implement that field — it instead hardcodes the
distinction as "hard whenever the submission's class code contains
'roofing', soft otherwise" (`decision_core/matching.py`'s
`_severity_is_hard`). This matches every worked example in the sample
dataset, but is a narrower rule than the guide's fully general
per-carrier-configurable version, and should be revisited before onboarding
any carrier panel where severity-ceiling hardness doesn't line up cleanly
with class name.

---

## 7. Data Schema

### 7.1 Carrier Appetite Profile (input, one JSON file per carrier)

```json
{
  "carrier_id": "string",
  "carrier_name": "string",
  "class_codes_accepted": ["string"],
  "class_codes_excluded": ["string"],
  "states_licensed": ["string, two-letter abbreviation"],
  "premium_band": {"min": "number", "max": "number"},
  "submission_requirements": {
    "min_loss_run_years": "integer",
    "required_documents": ["string"],
    "acceptance_window_days": "integer, nullable"
  },
  "severity_ceiling": {"max_single_claim_incurred": "number"},
  "appetite_confidence": "high | medium | low",
  "historical_hit_rate_this_class": "number, 0-1",
  "lines_written": ["string"],
  "notes": "string"
}
```

### 7.2 Market Matching Output (this workflow's `OutputPackage.payload`)

```json
{
  "submission_id": "string, nullable",
  "matches": [
    {
      "carrier_id": "string",
      "carrier_name": "string",
      "score": "number",
      "missing": ["string, specific missing/incomplete items"],
      "flags": ["string, informational notes (near premium edge, over soft severity ceiling, etc.)"]
    }
  ],
  "excluded": [
    {
      "carrier_id": "string",
      "carrier_name": "string",
      "rule": "string, e.g. MM-01 | MM-02 | MM-03 | MM-04 | MM-05",
      "reason": "string, specific reason this carrier was excluded"
    }
  ],
  "diligent_search": {
    "required": "boolean",
    "on_file": "integer, declination count found in extracted data",
    "compliant": "boolean, on_file >= 3",
    "note": "string"
  }
}
```

**On the diligent-search threshold:** v1 conservatively assumes documentation
is required for every submission (standard surplus-lines practice) since no
per-state diligent-search-requirement reference data was provided, and uses
a 3-declination-on-file threshold as this implementation's own reasonable
default for "documented diligent search complete" — neither of these is
stated in the source dataset/guide, and both should be validated against
real state-by-state requirements before this leaves prototype status.

---

## 8. Risks & Open Questions

| Risk | Mitigation / Owner |
|---|---|
| Carrier panel is a static, per-dataset JSON file — real carriers' appetite changes over time (new class codes accepted, premium bands adjusted, capacity pulled) and nothing in v1 keeps that data current | This is the same "who owns carrier profile freshness" question every downstream E&S workflow inherits (Package Assembly's PRD flags it again for the extended profile schema) — needs a real ownership/update-cadence answer during discovery, not solved by this PRD |
| MM-05's hard/soft severity distinction is hardcoded to "roofing" rather than configurable per carrier/class (see Section 6's "Known simplification") | Revisit before onboarding any carrier/class combination not already covered by the sample dataset's worked examples — add the guide's originally-proposed `ceiling_type` field if a real panel needs it |
| Diligent-search's "3 declinations = compliant" threshold and "required everywhere" default are this implementation's own reasonable assumptions, not sourced from real per-state legal requirements | Must be validated against actual state surplus-lines diligent-search statutes before this feeds any real compliance-facing decision — treated as a placeholder, same caveat as every rules document in this project |
| Completeness-vs-exclusion is the rule most likely to be implemented incorrectly under time pressure (per the interpretation guide's own framing) | Submission 01 in the sample dataset is a mandatory, non-skippable eval case for exactly this reason — should function as a release gate, not just a quality check, mirroring how Package Assembly treats its own auto-fill-boundary eval case |
| Zero-match handling (Submission 06) is the single most important failure mode to avoid getting wrong — a forced low-confidence match is worse than an accurate "no market found" | Same release-gate treatment as the completeness case above; both should be non-negotiable pre-launch eval cases |

---

## 9. Rollout Plan

1. **Discovery:** confirm real carrier panel composition and ownership/
   update cadence with the design partner; validate the ranking formula's
   weights against real broker priorities; validate the diligent-search
   threshold and "required everywhere" default against real state
   requirements.
2. **Build v0 (delivered):** hard-exclusion engine (MM-01/02/03/04), soft
   scoring engine (MM-05/06), independent diligent-search check (MM-07),
   ranked + excluded + compliance output, zero-match handling — all live
   today against the sample dataset's fixture panel and submissions.
3. **Shadow mode:** run real submissions against a real (not fixture)
   carrier panel in parallel with brokers' current manual screening; compare
   ranked output and exclusion reasoning against what brokers actually did.
4. **Live pilot:** system output enters the real review queue, Section 2.3
   metrics tracked weekly, with the zero-false-inclusion and zero-forced-
   match gates treated as non-negotiable throughout.
5. **Go/no-go review:** against Section 2.3 criteria — only then treat
   Package Assembly (which already consumes this workflow's output format
   today) as validated against real, not just fixture, upstream data.

---

*This document defines v1 scope only, written to describe the system as
implemented. The carrier-panel staleness risk, the hardcoded roofing-based
MM-05 simplification, and the diligent-search threshold/requirement
assumptions are the three open items most likely to need real-world
validation before this leaves prototype status — see Section 8.*
