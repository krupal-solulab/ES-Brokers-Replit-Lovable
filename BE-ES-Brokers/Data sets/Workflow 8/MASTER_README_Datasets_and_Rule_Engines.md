# Coverline — Master Guide to Datasets & Rule Engines

**Purpose of this document:** every workflow built so far comes with its
own PRD, sample dataset, and (for most) a rule interpretation guide.
This document is the index that ties them together — it explains the
conventions used across all of them, the principles that recur in every
rule engine, and where to find each workflow's specific materials. Read
this first before opening any individual dataset; it'll save you from
re-deriving patterns that are actually consistent across the whole
project.

---

## 1. How every dataset is structured

Every dataset (whether zipped or in a folder) follows the same shape:

```
{workflow}_dataset/
  README.md                              <- scenario-by-scenario summary,
                                             what each one tests, expected outcome
  RULE_ENGINE_INTERPRETATION_GUIDE.md     <- rule-by-rule explanation of HOW
    (or TONE_FRAMING_RULES_GUIDE.md          to apply each rule correctly
     for communication-drafting workflows)
  scenario_01/ (or submission_01/,
    trigger_01/, renewal_01/)
    - input file(s): email text, structured JSON, or both
    - expected_output / expected_draft / expected_*.txt
      <- what the correct system output should look like, WITH
         explanatory notes attached (not just the raw answer)
  scenario_02/
  ...
```

**The pattern to internalize:** the `README.md` tells you *what* each
scenario is testing and what the expected outcome is. The
`RULE_ENGINE_INTERPRETATION_GUIDE.md` tells you *why* the rule works
that way and what mistake it's specifically designed to catch. The
`expected_output` files show both the correct answer AND embedded notes
explaining the reasoning — these notes are as important as the answer
itself, since they're what makes a scenario useful for debugging a wrong
implementation, not just checking a final score.

---

## 2. Principles that recur across every rule engine

These aren't restated in full in every individual guide, but they
apply everywhere. If you only read one section of this document, read
this one.

### 2.1 Grounding — never state a fact without a source
Every workflow, every rule engine, every communication draft: any claim
made about a submission, a carrier, a quote, or a policy must trace back
to a specific extracted field or logged record. This is stated
explicitly in nearly every PRD's Functional Requirements section
(usually an FR titled something like "grounding/citation requirement"),
and it's the single most repeated constraint in the entire project.
When in doubt about whether a system output is allowed to say something,
the test is: *can this be traced to an actual source, or is it a
plausible-sounding inference?* If it's the latter, it doesn't belong in
the output.

### 2.2 Human approves every consequential action, permanently
No workflow in this project auto-sends an email, auto-binds a policy,
auto-executes a carrier submission, or auto-edits substantive reference
data (like a Carrier Appetite Profile's accepted/excluded class lists).
This is not a v1 limitation anywhere it appears — it's a permanent
architectural boundary, stated most explicitly in the Broker
Communication PRDs (MGA and Wholesale) and the Carrier Appetite
Intelligence PRD. If you see a proposal to automate past this boundary
for any workflow, that's a new product decision requiring its own
deliberate scoping, not an assumed next step.

### 2.3 Absence of data is not the same as exclusion
This shows up under different rule names in different workflows (Market
Matching's MM-04, Endorsement Processing's EP-02, Diligent Search's
DS-02) but it's the same underlying principle every time: when a data
point is missing — a class code not on any list, a document not yet
provided, a declination not yet documented — the system must treat that
as an **explicit open question**, never silently defaulted to either
"probably fine" or "probably excluded." Look for this pattern any time
you see a rule engine describing three possible outcomes instead of two.

### 2.4 An external party's document is data to verify, not ground truth
First established in Binder & Policy Issuance Coordination (BI-03,
BI-05) and extended into Endorsement Processing (EP-05): a carrier's
bind confirmation, issued policy, or issued endorsement is never
auto-trusted just because it's official. Every workflow that reconciles
against a carrier-issued document treats that document as something to
check field-by-field against what was actually requested, not something
to accept at face value.

### 2.5 Low-confidence or low-volume output must say so
Whether it's a low-confidence document extraction (routes to manual
review across nearly every workflow), a low-volume carrier hit-rate
(Pipeline Reporting's PR-02), or a single-data-point signal (Carrier
Appetite Intelligence's CI-05), the rule is the same: **the system must
surface its own uncertainty rather than presenting a number or a
recommendation with more confidence than the underlying data supports.**
This principle traces directly back to the very first critique in this
entire project — the original Coverline landing page's fabricated
"142 submissions today" dashboard stats — and it recurs as an explicit
rule in nearly every workflow built since.

### 2.6 Every threshold in every rule engine is a placeholder
Dollar amounts, day counts, percentage thresholds, confidence cutoffs —
none of these were derived from real operational data. They exist to
make the sample datasets' scenarios unambiguous for testing purposes.
Every PRD says this explicitly in its Rule Engine section, and it's
worth repeating here because it's easy to forget after reading a dozen
specific-sounding numbers: **validate every threshold with the actual
design partner during discovery before treating any of them as
production-ready.**

---

## 3. Common mistakes worth watching for across implementations

Pulled from the interpretation guides' recurring warnings:

- **Collapsing a three-outcome check into a binary one** (Market
  Matching's exclusion-vs-scoring distinction, Endorsement Processing's
  appetite three-outcome model, Renewal Remarketing's four-state trigger
  decision) — the most common way these rule engines get implemented
  wrong under time pressure.
- **Treating a carrier-provided convenience (like "this field is
  auto-fillable") as license to infer rather than extract** (Package
  Assembly's PA-02) — the single most consequential rule to get right
  in that workflow, and a pattern worth remembering elsewhere.
- **Scoring an account-specific outcome the same as a class-level
  pattern** (Carrier Appetite Intelligence's CI-02) — the difference
  between real signal and normal variance.
- **Reusing one cover letter/comparison template across multiple
  carriers or options instead of evaluating each independently** (MGA
  Broker Communication, Package Assembly's Scenario 03, Quote
  Comparison's QC-01) — shows up repeatedly because it's a natural
  engineering shortcut that produces subtly wrong output.
- **Smoothing over a data gap to produce a cleaner-looking report**
  (Pipeline Reporting's PR-06) — the most direct descendant of the
  project's founding lesson about fabricated-looking statistics.

---

## 4. Index of everything built so far

### MGA Vertical

| Workflow | PRD | Dataset | Rules location |
|---|---|---|---|
| Submission Triage | `PRD_MGA_Underwriting_Triage_Copilot.md` | `test_dataset/` | `Validation_Rules_Test_Dataset.md` (top-level, separate file) |
| Renewal Management | `PRD_Renewal_Management_Copilot.md` | `renewal_dataset/` | Embedded in PRD, Section 6 |
| Broker Communication | `PRD_Broker_Communication_Copilot.md` | `broker_comm_dataset/` | Embedded in PRD, Section 6 (tone rules TN-01–17) |

*Note: the MGA workflows predate the convention of a standalone rule
guide file — their rules are either in a separate top-level document
(Triage) or embedded directly in the PRD (Renewal, Broker Comm). Read
the relevant PRD's Section 6 directly for these three.*

### Wholesale/E&S Vertical

| Workflow | PRD | Dataset | Rules location |
|---|---|---|---|
| Submission Market Matching | `PRD_Submission_Market_Matching_Copilot.md` | `market_matching_dataset/` | `RULE_ENGINE_INTERPRETATION_GUIDE.md` inside dataset |
| Submission Package Assembly | `PRD_Submission_Package_Assembly_Copilot.md` | `package_assembly_dataset/` | same pattern |
| Retail Agent Communication | `PRD_Retail_Agent_Communication_Copilot.md` | `retail_comm_dataset/` | `TONE_FRAMING_RULES_GUIDE.md` inside dataset |
| Quote Comparison & Recommendation | `PRD_Quote_Comparison_Recommendation_Copilot.md` | `quote_comparison_dataset/` | `RULE_ENGINE_INTERPRETATION_GUIDE.md` inside dataset |
| Binder & Policy Issuance Coordination | `PRD_Binder_Policy_Issuance_Coordination_Copilot.md` | `binder_issuance_dataset/` | same pattern |
| Endorsement / Mid-Term Change Processing | `PRD_Endorsement_MidTerm_Change_Processing_Copilot.md` | `endorsement_dataset/` | same pattern |
| Renewal Remarketing | `PRD_Renewal_Remarketing_Copilot.md` | `renewal_remarketing_dataset/` | same pattern |
| Diligent Search & Compliance Documentation | `PRD_Diligent_Search_Compliance_Documentation_Copilot.md` | `diligent_search_dataset/` | same pattern |
| Carrier Appetite Intelligence Tracking | `PRD_Carrier_Appetite_Intelligence_Copilot.md` | `carrier_intelligence_dataset/` | same pattern |
| Pipeline & Carrier Performance Reporting | `PRD_Pipeline_Carrier_Performance_Reporting_Copilot.md` | `pipeline_reporting_dataset/` | same pattern |

### Supporting strategy documents (not workflow-specific)

- `Coverline_MGA_10_Workflow_Roadmap.md` — sequencing and leverage analysis for the MGA vertical
- `Coverline_Wholesale_ES_10_Workflow_Roadmap.md` — same, for Wholesale/E&S
- `Architecture_Delta_MGA_to_Wholesale.md` — what's reused vs. new when extending Coverline's core across verticals
- `Coverline_Landing_Page_Structure.md` and `Coverline_Lovable_Prompts.md` — product positioning and page-build materials
- `PRD_TPA_Claims_Summarization_Copilot.md` — the shelved third vertical, kept for reference

---

## 5. How to actually use this when implementing a workflow

1. **Read the PRD's Problem Statement and Scope sections first** — don't start with the rule engine in isolation, since the rules only make sense against the workflow's actual job.
2. **Read the workflow's rule interpretation guide in full before writing any rule logic** — every guide exists specifically because the rule names/summaries in the PRD are not sufficient on their own to implement correctly; the interpretation notes contain the actual mistakes to avoid.
3. **Treat every scenario's `expected_output` file as a test case with an attached explanation, not just an answer key** — the embedded notes tell you which specific implementation shortcut would produce a wrong-but-plausible-looking result.
4. **Cross-reference Section 2 of this document (recurring principles) against whatever you're building** — most implementation mistakes across this whole project are violations of one of those six principles, not workflow-specific errors.
5. **Never treat a threshold, dollar figure, or day-count in any rule engine as production-ready** — every single one requires discovery-phase validation with a real design partner, per Section 2.6.

---

## 6. The thing worth repeating one more time

Every dataset, every rule guide, every PRD in this index was built from
research and internally consistent reasoning — not from a validated
conversation with a real MGA underwriter or wholesale broker. This
master guide makes the *documentation* easier to navigate; it does not
make the underlying workflows validated. Treat everything here as a
well-organized starting point for a real design partner conversation,
not as a finished specification ready for unmodified implementation.
