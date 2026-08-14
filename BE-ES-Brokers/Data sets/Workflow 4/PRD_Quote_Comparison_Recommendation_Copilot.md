# PRD: Quote Comparison & Recommendation Copilot (v1)
## Wholesale/E&S Broker Vertical

**Status:** Draft for engineering scoping
**Owner:** [Product]
**Last updated:** 2026-07-16
**Depends on:** Submission Market Matching (v1) and Submission Package Assembly (v1) — this workflow picks up the placement process exactly where those two leave off, once carrier responses (quotes or declinations) start arriving. It also feeds the Retail Agent Communication Copilot's Quote/Terms Summary trigger, replacing that workflow's v1 manual-input fallback with real structured data.

---

## 1. Problem Statement

Once a wholesale broker has approached one or more carriers with a package, responses come back — quotes with specific terms, subjectivities, and validity windows, or declinations. Today, a broker manually reads each response, mentally compares terms across carriers (often on inconsistent structures — different deductibles, different endorsement inclusions, different subjectivities), and decides what to present to the retail agent. This is genuinely harder than it looks: a lower premium can hide materially worse terms, a routine-looking subjectivity can carry a hidden deadline that threatens the whole placement, and a good quote sitting unactioned past its validity window is a real, avoidable lost placement. This is also the point in the process furthest from Coverline's existing extraction core — it's new domain logic, not a reuse of what's already built.

**Goal of v1:** Ingest carrier response emails (quotes and declinations), normalize terms for genuine comparability, classify subjectivities by materiality, track quote validity windows actively, and produce either a single clear recommendation or an explicit multi-option trade-off — for broker review, feeding directly into the Retail Agent Communication Copilot's Quote/Terms Summary.

**Explicitly not the goal of v1:** Negotiating with carriers, automatically selecting or binding a quote, or generating the final bind order/policy issuance paperwork (that's the next workflow on the roadmap, Binder & Policy Issuance Coordination).

---

## 2. Scope of v1

### 2.1 In scope
- Ingesting carrier response emails (quotes and declinations) for a submission already tracked through Market Matching/Package Assembly
- Extracting structured quote terms: premium, limits, deductible, key endorsements, subjectivities, effective date, quote validity window
- Term normalization and comparability assessment across multiple quotes (Section 6, QC-01)
- Subjectivity materiality classification (routine vs. timeline-affecting)
- Declination handling, including consistency-checking against the carrier's known appetite profile (informational logging only in v1 — see Section 2.2)
- Quote validity window tracking with proactive urgency alerts, independent of whether a comparison is relevant
- Recommendation output: single primary recommendation or explicit multi-option trade-off, per configurable weighting
- Feeds the Retail Agent Communication Copilot's Quote/Terms Summary trigger directly (removing that workflow's v1 manual-input dependency)

### 2.2 Explicitly out of scope for v1
- Automated quote acceptance or bind instruction to a carrier — this workflow ends at a broker-reviewed recommendation, same permanent human-approval boundary as every prior Coverline workflow
- Acting on declination-consistency signals (Section 6, QC-03) beyond logging them — this is explicitly deferred groundwork for the future Carrier Appetite Intelligence workflow, not a v1 capability
- Negotiating or requesting revised terms from a carrier on the broker's behalf
- Multi-line quote comparison (a submission spanning GL + Property should be compared as two separate passes in v1, consistent with the same scope boundary set in the Market Matching PRD)
- Client-facing (as opposed to retail-agent-facing) output — this workflow's output feeds Retail Agent Communication, not a separate client-facing document

### 2.3 Success criteria (must hit before expanding scope)
- **Zero misleading premium-only comparisons:** 0% of multi-quote comparisons in the pre-launch eval should present a premium difference without flagging any underlying term mismatch (deductible, limits, endorsement scope) — this is the direct analog to Market Matching's zero-false-positive gate, applied to comparison logic instead of matching logic
- **Material subjectivity detection recall:** ≥95% of genuinely timeline-affecting subjectivities in the eval set must be correctly flagged as material rather than routine — a missed material subjectivity risks a real placement deadline
- **Zero missed validity-window alerts:** 100% of quotes approaching expiration with no broker action logged must trigger an urgency alert — hard quality gate, mirroring the same seriousness given to other timing-sensitive checks across this vertical (Market Matching's MM-07, Renewal Management's lapse-risk rule)
- **Recommendation usability:** ≥80% of the workflow's mode selection (single-recommendation vs. multi-option) agrees with what an experienced broker would independently choose, measured against a held-out historical sample

---

## 3. Users & Personas

| Persona | Role in this workflow |
|---|---|
| **Wholesale Broker / Production Underwriter** (primary user) | Reviews comparison/recommendation output, decides which quote(s) to present to the retail agent |
| **Brokerage Principal / Managing Partner** (secondary) | Cares about placement close rate and whether brokers are systematically getting the best available terms for clients |
| **Retail Agent** (indirect, downstream recipient) | Ultimately receives the Quote/Terms Summary this workflow's output feeds, per the Retail Agent Communication Copilot |

---

## 4. End-to-End Workflow

```
1. Carrier response(s) arrive via email — quote(s) and/or declination(s)
   — for a submission already tracked through Market Matching/Package
   Assembly
2. System ingests and classifies each response (quote vs. declination)
3. For quotes: extract structured terms (premium, limits, deductible,
   endorsements, subjectivities, effective date, validity window)
4. For declinations: extract stated reason if given, and check
   consistency against that carrier's known appetite profile (Section
   6, QC-03) — log only, no action taken in v1
5. Run Term Normalization (QC-01): assess whether multiple quotes are
   genuinely comparable on premium alone, or whether limits/deductible/
   endorsement differences require trade-off framing
6. Run Subjectivity Classification (QC-02): tier each condition as
   routine or material/timeline-affecting
7. Run Quote Validity Tracking (QC-07): check remaining time on each
   quote's validity window against current date and logged broker
   action — this runs regardless of whether a multi-quote comparison
   exists (Section 6's key architectural point)
8. Determine output mode (QC-06): single primary recommendation, or
   explicit multi-option trade-off — driven by whether QC-01 found a
   genuine trade-off, not defaulted to whichever produces cleaner output
9. Present output to broker: either a comparison view (2+ quotes) or a
   single-quote status view, with urgency prominently surfaced wherever
   QC-07 flags it
10. Broker reviews, decides which quote(s) to present to the retail
    agent (or to request revised terms — outside this workflow's scope)
11. Broker's decision feeds directly into the Retail Agent Communication
    Copilot's Quote/Terms Summary trigger (replacing that workflow's
    v1 manual-input fallback, per FR-2 in that PRD)
12. System logs: comparison output, broker's actual selection, and
    (where trackable) eventual bind outcome — same Feedback/Eval Store
    pattern as every prior workflow
```

**Design principle, consistent with every workflow in this vertical:**
the system compares, classifies, and flags urgency; the broker decides.
This workflow doesn't change that boundary — what's different here is
that the underlying comparison logic (QC-01 through QC-07) is genuinely
new domain reasoning, not a variation on the extraction/matching/
assembly patterns reused everywhere else in this vertical so far.

---

## 5. Functional Requirements

### 5.1 Carrier Response Ingestion

- **FR-1:** System must ingest carrier response emails and classify each as a quote or declination.
- **FR-2:** System must associate each response with the correct existing submission (matching on named insured + carrier + submission reference, consistent with the matching patterns established in earlier workflows).
- **FR-3:** System must handle responses arriving asynchronously and at different times for the same submission — a comparison should update as each new response arrives, not require all responses to be present before producing any output (per Scenario 06's single-quote case, which is a fully valid, complete state on its own).

### 5.2 Quote Term Extraction

- **FR-4:** Extract structured fields per Section 7.1's schema: premium, limits, deductible(s), key endorsements (additional insured, waiver of subrogation, and others as configured per line of business), effective date, subjectivities (as a list, not a single text blob), and quote validity window.
- **FR-5:** Where a standard field is not clearly stated in a carrier's response, flag it as "not stated" rather than assuming continuity with the original submission's requested terms, per QC-05 — this is a hard grounding requirement, not a style preference.
- **FR-6:** Every extracted field must be traceable back to the specific carrier response it came from, consistent with the citation/grounding standard established across every Coverline workflow.

### 5.3 Term Normalization & Comparability

- **FR-7:** When 2+ quotes exist for the same submission, run the comparability check (QC-01) before generating any premium-based comparison — this check must complete and its result must gate what kind of comparison output is produced, not run as an optional afterthought.
- **FR-8:** Any comparison output involving quotes with differing limits, deductibles, or material endorsement structure must explicitly frame the trade-off (per QC-01/QC-06) rather than presenting premium as the primary or sole comparison point.

### 5.4 Subjectivity Classification

- **FR-9:** Extract every subjectivity/condition from each quote as a distinct, individually-classified item (not a single combined text field) — classification per QC-02 into routine vs. material/timeline-affecting.
- **FR-10:** Material subjectivities must be surfaced with their specific deadline or dependency clearly stated (e.g., "inspection must be scheduled within 10 days of quote acceptance"), not just flagged as "material" without the actionable detail attached.

### 5.5 Declination Handling

- **FR-11:** Extract the stated reason for a declination where the carrier provides one; if no reason is given, log this explicitly rather than leaving the field blank without indication.
- **FR-12:** Check declination consistency against the carrier's known Carrier Appetite Profile (per QC-03) — log whether the declination is "consistent with known appetite" or "inconsistent with known appetite" as a distinct, queryable field, even though v1 takes no action on this signal beyond logging it.
- **FR-13:** A declination that leaves only one viable quote for a submission must shift the output mode to single-option (per QC-06), not continue presenting a comparison-shaped output with a "declined" placeholder in place of a real option.

### 5.6 Quote Validity Tracking

- **FR-14:** Track each quote's stated validity window against the current date, independent of whether other quotes exist for the same submission (per QC-07 — this must run even in single-quote scenarios).
- **FR-15:** Generate a proactive urgency alert when a quote's remaining validity falls below a configurable threshold (default: 5 business days) AND no broker action has been logged against it — this should surface at a higher priority than routine comparison output in the broker's queue.
- **FR-16:** Where a quote's subjectivities include a dependency on another action (e.g., "primary carrier binding confirmed," per Scenario 06), check and surface whether that dependency is itself resolved, not just the quote's own validity date.

### 5.7 Recommendation Generation

- **FR-17:** Determine output mode — single primary recommendation or multi-option trade-off — per QC-06's decision logic, defaulting to multi-option whenever a genuine, non-dominant trade-off exists rather than forcing a single winner for the sake of a cleaner-looking output.
- **FR-18:** Recommendation weighting (price vs. terms breadth vs. subjectivity burden vs. carrier reliability) must be configurable per QC-04, not hardcoded to a single-factor default — validate actual weights with the design partner's brokers during discovery.
- **FR-19:** Every recommendation must be grounded and cited to the specific extracted quote terms driving it, consistent with the standard established across every Coverline workflow.

### 5.8 Downstream Integration

- **FR-20:** This workflow's output must be consumable directly by the Retail Agent Communication Copilot's Quote/Terms Summary and Placement Confirmation triggers, replacing that workflow's v1 manual-input fallback (per that PRD's FR-2 and Section 9 risk register) — this is a meaningful improvement to that workflow's data reliability and should be treated as a integration priority, not an optional nice-to-have.

### 5.9 Human Review Interface

- **FR-21:** Comparison/recommendation view: side-by-side quote terms with comparability status clearly indicated, subjectivities tiered by materiality, validity windows and urgency prominently displayed.
- **FR-22:** Single-quote urgency alerts (per FR-15) must be visually and positionally distinct from routine comparison output — a broker should never have to open a "comparison" to discover a single expiring quote; it should surface proactively.
- **FR-23:** One-click actions: broker marks which quote(s) to present to the retail agent, which feeds FR-20's downstream trigger; broker can also mark "requesting revised terms" or "no action, quote will lapse" for logging purposes.
- **FR-24:** All broker decisions logged for the feedback loop, consistent with every prior Coverline workflow's pattern.

### 5.10 Non-Functional Requirements

- **FR-25:** Processing time per carrier response: target < 5 minutes from receipt to structured extraction, consistent with the lighter-weight workflows in this vertical (this is closer to Package Assembly's speed than Market Matching's, since it's processing one response at a time, not running a full panel match).
- **FR-26:** Validity-window monitoring (FR-14/FR-15) must run as an ongoing scheduled check, not only at the moment a quote is first ingested — a quote that looked fine on day one needs to be re-checked as its validity window approaches, similar in architecture to the Renewal Trigger Service pattern from the MGA Renewal Management PRD.
- **FR-27:** Same data retention, encryption, and access-control requirements as every prior Coverline workflow.

---

## 6. Rule Engine

**See the companion document, `RULE_ENGINE_INTERPRETATION_GUIDE.md`, for
full interpretation notes and worked examples against the sample
dataset.** Summary:

| Rule ID | Rule | Type |
|---|---|---|
| QC-01 | Term normalization for comparability | Gates whether premium comparison is valid on its own |
| QC-02 | Subjectivity/condition extraction and materiality flagging | Two-tier classification: routine vs. timeline-affecting |
| QC-03 | Declination handling and appetite-consistency signal capture | Logged only in v1, feeds future Carrier Appetite Intelligence |
| QC-04 | Recommendation basis weighting | Configurable, never single-factor-default |
| QC-05 | Missing/incomplete quote data handling | Flag, never assume continuity with original request |
| QC-06 | Multi-option vs. single-recommendation mode selection | Defaults to multi-option whenever a genuine trade-off exists |
| QC-07 | Quote validity window tracking | Runs independent of comparison relevance — a first-class output shape, not an edge case |

**All thresholds (the 5-business-day validity alert default, the
comparability tolerance for what counts as a "material" term
difference) are placeholders**, consistent with every rules document in
this project, and must be validated with the design partner's brokers
during discovery.

---

## 7. Data Schemas

### 7.1 Extracted Quote Schema

```json
{
  "quote_id": "string",
  "submission_id": "string",
  "carrier_id": "string",
  "carrier_name": "string",
  "response_type": "QUOTE | DECLINATION",
  "premium": "currency, null if declination",
  "limits": "string, null if declination",
  "deductibles": {"all_perils": "currency, null if N/A", "wind_hail": "currency, null if N/A"},
  "key_endorsements": [{"type": "string", "basis": "included_blanket | scheduled_only | additional_premium | not_offered"}],
  "subjectivities": [
    {"description": "string", "materiality": "routine | material", "deadline_or_dependency": "string, null if none"}
  ],
  "effective_date": "date, null if declination",
  "quote_valid_through": "date, null if declination",
  "declination_reason": "string, null if quote",
  "declination_appetite_consistency": "consistent | inconsistent | unable_to_determine, null if quote",
  "source_email_reference": "string, for citation/grounding"
}
```

### 7.2 Comparison/Recommendation Output Schema

```json
{
  "submission_id": "string",
  "named_insured": "string",
  "quotes_considered": ["list of quote_id"],
  "comparability_assessment": {
    "directly_comparable": "boolean",
    "material_differences": ["list of strings, e.g. 'deductible', 'endorsement structure'"]
  },
  "output_mode": "SINGLE_RECOMMENDATION | MULTI_OPTION | SINGLE_QUOTE_URGENT | SINGLE_QUOTE_ROUTINE",
  "recommendation": {
    "primary_quote_id": "string, null if multi-option",
    "reasoning": {"summary": "string", "citations": [{"claim": "string", "source": "string"}]}
  },
  "urgency_flags": [
    {"quote_id": "string", "flag_type": "validity_window | material_subjectivity | dependency_unresolved", "detail": "string"}
  ],
  "processing_metadata": {"last_updated_timestamp": "datetime"}
}
```

---

## 8. System Architecture (Level 2)

```
┌───────────────────────────┐
│ Carrier Response Ingestion    │  (new — email classification into
│ (quote / declination)          │   quote vs. declination)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Quote Term Extraction          │  (NEW extraction target — different
│                                 │   from ACORD/loss-run extraction,
│                                 │   this is unstructured carrier-reply
│                                 │   email parsing)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Term Normalization Engine      │◄─────┤ Original Submission Data       │
│ (QC-01)                        │      │ (from Market Matching/Package  │
└────────────┬─────────────────┘      │  Assembly, for context)         │
             │                          └───────────────────────────┘
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Subjectivity Classification    │      │ Carrier Appetite Profile DB    │
│ Engine (QC-02)                 │      │ (existing, from Market         │
└────────────┬─────────────────┘      │  Matching — used for QC-03      │
             │                          │  declination consistency check) │
             ▼                          └───────────────────────────┘
┌───────────────────────────┐
│ Declination Consistency Check  │  (QC-03 — logging only in v1)
│ (QC-03)                        │
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Quote Validity Monitor         │  (QC-07 — runs on an ongoing
│ (scheduled, ongoing check,     │   schedule, not just at ingestion,
│  per FR-26)                    │   per the Renewal Trigger Service
│                                 │   architectural pattern)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Recommendation Engine          │  (QC-04, QC-06 — mode selection +
│                                 │   weighted recommendation)
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐
│ Broker Review Interface        │◄──── Decisions logged here
│ (comparison view + urgent      │
│  single-quote alerts, per      │
│  FR-21/FR-22)                  │
└────────────┬─────────────────┘
             ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│ Feedback/Eval Store             │      │ Retail Agent Communication     │
│                                  │──────►│ Copilot (Quote/Terms Summary   │
│                                  │      │  trigger, per FR-20)            │
└───────────────────────────────┘      └───────────────────────────────┘
```

**Key architectural point, different from every other workflow in this
vertical so far:** this is the first workflow where the extraction
target is genuinely new (carrier response emails, not ACORD/loss-run/
financials), and the comparison/normalization logic (QC-01, QC-06) has
no equivalent anywhere else in Coverline's build so far — it's not a
reuse of the appetite-matching pattern from Market Matching, it's a
different kind of reasoning (comparing offers against each other rather
than against a fixed appetite standard). Budget engineering effort
accordingly; this should not be estimated as "another lightweight
workflow" the way Package Assembly and Retail Agent Communication were.

---

## 9. Risks & Open Questions

| Risk | Mitigation / Owner |
|---|---|
| Carrier response emails are unstructured, free-text, and formatted inconsistently across carriers — likely as much format variance as loss runs, if not more, since there's no ACORD-equivalent standard for quote responses | Treat this as the "loss run format variance" risk of this PRD, per the pattern already established in the MGA Submission Triage PRD — budget real engineering and eval effort here specifically, and expect this to be a meaningfully larger extraction challenge than Market Matching's structured ACORD-based inputs |
| QC-01's comparability assessment requires domain judgment about which term differences are "material" — a wind/hail deductible difference matters enormously for a coastal property account and much less for an inland one | This threshold likely needs to vary by line of business and even by specific risk characteristics (coastal proximity, in Scenario 02's case) — validate with real brokers during discovery rather than using a single global materiality threshold |
| QC-03's declination-consistency logging is designed as groundwork for the future Carrier Appetite Intelligence workflow, but if that workflow is delayed indefinitely, this logging becomes dead weight with no consumer | Revisit whether QC-03's full logging infrastructure is worth building in v1, or whether a lighter-weight version (just capturing the declination reason as free text) is sufficient until Carrier Appetite Intelligence is actually prioritized — a genuine scope question worth raising during discovery rather than assuming the fuller version is justified |
| FR-20's integration into Retail Agent Communication changes that workflow's behavior (removing its manual-input fallback) — this creates a cross-workflow dependency that needs coordinated testing, not just independent testing of each workflow in isolation | Explicitly test the Quote Comparison → Retail Agent Communication handoff end-to-end during this workflow's pilot phase, not just this workflow's own output in isolation |
| Quote validity monitoring (FR-26) is the first ongoing/scheduled background process in this vertical outside of Market Matching's carrier-profile staleness check — confirm the underlying infrastructure (scheduled jobs, not just event-triggered processing) is architected for this from the start | Flag as a discovery/architecture planning item; this is a different execution model from every prior workflow's purely event-driven design |

---

## 10. Rollout Plan

1. **Discovery (2 weeks):** sample real carrier response emails from the design partner's history to assess actual format variance (per the top risk above), validate comparability materiality thresholds with real brokers, confirm recommendation weighting preferences (QC-04).
2. **Build v0 (4-5 weeks — longer than Package Assembly or Retail Agent Communication, given the genuinely new extraction and comparison logic):** Carrier Response Ingestion, Quote Term Extraction, Term Normalization Engine, Subjectivity Classification, Declination Consistency Check (lightweight per the Section 9 scope question), Quote Validity Monitor, Recommendation Engine, review UI.
3. **Shadow mode (2-3 weeks):** run against real incoming carrier responses in parallel with brokers' normal manual comparison process.
4. **Live pilot (4 weeks):** system output enters the real review queue and feeds Retail Agent Communication live, Section 2.3 metrics tracked weekly, with particular attention to the zero-misleading-comparison gate.
5. **Go/no-go review:** against Section 2.3 criteria — only then consider Binder & Policy Issuance Coordination (the next workflow on the vertical roadmap) as the natural following build, since it picks up exactly where a broker's quote selection leaves off.

---

*This document defines v1 scope only. Automated carrier negotiation, quote acceptance/bind instruction, and any capability that acts on (rather than merely logs) declination-consistency signals should be treated as new PRD scope — the last of these in particular is the entry point to the deferred Carrier Appetite Intelligence workflow and deserves the same careful, deliberate scoping already called out as a risk in the Market Matching and Architecture Delta documents.*
