# Rule Engine Interpretation Guide — Submission Market Matching

**Purpose of this document:** the PRD defines *what* the rules are. This
document explains *how to read and apply them correctly* — the
distinctions that are easy to implement wrong even with the rule
definitions in hand. Read this alongside the PRD's Section 6, not as a
replacement for it.

---

## The most important distinction in this whole rule engine: exclusion vs. scoring

Every other MGA rule engine we've built (Triage, Renewal) had a mix of
hard rules (pass/fail) and soft signals (feed into narrative judgment).
This one has a **three-tier** structure, and getting the tiers right is
the single most consequential implementation decision in this workflow:

1. **Hard exclusion (MM-01, MM-04):** the carrier does not appear in the
   ranked output at all. Not ranked last, not shown with a low score —
   absent. This applies to class-code exclusions and state-licensing
   mismatches. There is no version of "close enough" here: a carrier
   that excludes habitational should never appear in a habitational
   submission's ranked list, full stop, regardless of how good a fit the
   account is otherwise.
2. **Soft scoring factors (MM-02 partial, MM-05, MM-06):** the carrier
   *does* appear in the ranked list, but its position is affected —
   severity ceiling proximity, submission completeness, historical hit
   rate all adjust rank without eliminating the carrier outright.
3. **Informational flags (MM-03 edge cases, MM-07):** these don't affect
   ranking at all — they attach additional information to a carrier
   that's already ranked (e.g., "premium is at the low end of this
   carrier's band, expect scrutiny") or apply independently of ranking
   entirely (diligent search documentation).

**Common implementation mistake to avoid:** treating "carrier requires
5-year loss run, submission has 3 years" as a hard exclusion (tier 1)
rather than a scoring/completeness factor (tier 2). This is wrong, and
Submission 01 in the sample dataset is specifically built to catch this
error — Meridian and Palmetto should still appear in the ranked list for
that submission, just lower than Ironclad and with an explicit
missing-info note, not filtered out entirely. A broker would still want
to know Meridian is otherwise a great class/appetite fit even if the
loss run needs supplementing — filtering it out entirely hides a
potentially better long-term market relationship just because the
document package isn't complete yet.

---

## Rule-by-rule interpretation

### MM-01 — Class code match (Hard exclusion)
**What it checks:** does the submission's class code appear in the
carrier's `class_codes_accepted` list, and does it NOT appear in
`class_codes_excluded`?

**Interpretation note:** class code matching should not be pure string
matching. "Contractors - roofing (all types, steep and low slope)" and
"contractors - roofing (low slope only)" are meaningfully different
scopes even though both contain "roofing" — Palmetto (CAR-02) accepts
low-slope roofing specifically and should NOT be matched to a steep-slope
account (see Submission 05). This needs semantic/scoped matching, not
keyword matching, or you will produce false-positive matches that waste
a broker's time and damage the carrier relationship when the submission
bounces.

### MM-02 — State licensing match (Hard exclusion)
**What it checks:** is the submission's state of operation in the
carrier's `states_licensed` list?

**Interpretation note:** for multi-state submissions (a business
operating in several states), this should exclude a carrier only if the
carrier lacks licensing for **any** state where coverage is actually
needed — a carrier licensed in 5 of 6 states the business operates in is
still a hard exclusion for a blanket policy request, not a partial match,
unless the submission can reasonably be structured as state-specific
coverage (which is a judgment call that should route to a human, not be
auto-decided).

### MM-03 — Premium band fit (Hard exclusion at both ends, informational near the edges)
**What it checks:** does the submission's indicated premium fall within
`premium_band.min` and `premium_band.max`?

**Interpretation note — this is a hard exclusion, not a soft score,**
despite feeling similar to MM-05/MM-06 in spirit. Vantage Excess
Partners' $100K minimum isn't a preference, it's an underwriting
appetite boundary — Submission 03 ($2,400 indicated) and Submission 04
($340,000 indicated) are both designed to test that carriers get fully
excluded outside their premium band, not scored down. Where this
becomes informational rather than exclusionary: if a submission's
indicated premium sits within 10% of a carrier's band edge (configurable
threshold), attach an informational note ("near [carrier]'s premium
floor/ceiling — final quote may fall outside appetite") rather than
either excluding or presenting it with full confidence.

### MM-04 — Explicit class exclusion list (Hard exclusion)
**What it checks:** does the submission's class code appear on the
carrier's `class_codes_excluded` list, independent of whether it also
appears on the accepted list (exclusions should be checked first and
win in case of any data conflict).

**Interpretation note:** this is functionally similar to the negative
case of MM-01, but implemented as a separate rule deliberately — some
carrier appetite data sources will only provide exclusion lists (not
exhaustive inclusion lists), so the matching engine needs to handle
"accepted unless excluded" and "excluded unless explicitly accepted" as
two different data patterns depending on how a given carrier's appetite
profile was sourced/maintained. Don't assume every carrier profile has a
complete accepted-list; treat an empty or sparse accepted-list as "check
exclusions only" rather than "excludes everything not explicitly
listed."

### MM-05 — Severity ceiling (Soft scoring — but check carefully, this one is subtle)
**What it checks:** does any single claim in the submission's loss run
exceed `severity_ceiling.max_single_claim_incurred`?

**Interpretation note — this is the rule most likely to be implemented
incorrectly as a hard exclusion when it should usually be a strong
downward scoring factor instead**, EXCEPT when the carrier's own
appetite data explicitly signals it as a hard limit. Palmetto's
$150,000 ceiling against Summit Roofing's $310,000 open claim
(Submission 05) should result in Palmetto being excluded from the
ranking for that specific submission — but the *reason this is
correct* is that roofing severity ceilings are typically firm appetite
boundaries in this class, not a general rule that severity ceilings are
always hard exclusions across every class. Build this as configurable
per carrier/class combination (a `ceiling_type: hard | soft` field
should be added to the carrier profile schema, see Section 7 of the
PRD) rather than hardcoding severity as always-hard or always-soft.

### MM-06 — Submission completeness per carrier (Soft scoring + informational)
**What it checks:** does the submission include all documents in the
carrier's `submission_requirements.required_documents` list, and does
the loss run meet `min_loss_run_years`?

**Interpretation note:** this is the rule that produces the per-carrier
missing-info lists described in the PRD (FR-9). A carrier failing this
check should still rank based on its underlying appetite fit (class,
premium, severity), just with a visible "missing: [specific items]"
note attached — this is the completeness/ranking distinction from the
top of this document, applied concretely. Do not let a completeness gap
suppress a carrier's rank the same way a hard exclusion would.

### MM-07 — Diligent search / compliance documentation (Independent of ranking)
**What it checks:** does the submission's state require documented
evidence of admitted-market declination before E&S placement, and if
so, is that documentation present or does it need to be generated/
requested?

**Interpretation note — this is the one rule that fires regardless of
ranking outcome**, including in the true zero-match case (Submission
06). Even when no carrier on the panel is a fit, the system should still
check and flag whether diligent-search documentation exists or is
required for the state in question — a zero-match result doesn't mean
this workflow is "done," it means the broker still needs a documented,
compliant record of why no placement was found, which may itself be the
actual deliverable for that submission. Do not treat MM-07 as a
post-ranking nice-to-have; it needs to run on every submission
independent of whether MM-01 through MM-06 produce any matches at all.

---

## Ranking/scoring formula (for the carriers that survive hard exclusion)

For carriers that pass MM-01, MM-02, MM-03, and MM-04, compute a
composite score from:

```
score = (class_fit_specificity * 0.30)
      + (completeness_score * 0.25)        [from MM-06 — 1.0 if fully
                                             complete, decreasing per
                                             missing required item]
      + (historical_hit_rate * 0.25)        [from carrier profile]
      + (appetite_confidence_weight * 0.10) [high=1.0, medium=0.6,
                                             low=0.3 — penalizes stale
                                             or uncertain appetite data]
      + (severity_margin * 0.10)            [how much headroom exists
                                             below the severity ceiling,
                                             where applicable]
```

**These weights are placeholders**, consistent with every other rules
document in this project — validate against real wholesale broker
priorities during discovery (a broker might weight historical hit-rate
much higher than this default suggests, since a fast "yes" from a
lower-fit carrier can beat a slow "maybe" from a perfect-fit one,
depending on the broker's own priorities around placement speed vs.
placement quality).

---

## Summary — expected rule outcomes per sample dataset submission

| Submission | Rules primarily tested | Carriers excluded (hard) | Carriers ranked | Special flags |
|---|---|---|---|---|
| 01 | MM-06 (completeness ranking vs. exclusion) | None | Ironclad #1, Palmetto #2, Meridian #3 (Palmetto/Meridian flagged missing loss history) | None |
| 02 | MM-01/MM-04 (class exclusion) | Meridian, Palmetto, Ironclad, Apex, Vantage | Coastal Mutual only | None |
| 03 | MM-03 (premium floor) | Meridian, Palmetto, Ironclad, Coastal Mutual, Vantage | Apex Excess Lines only | None |
| 04 | MM-03 (premium ceiling) | Meridian, Palmetto, Apex, Coastal Mutual | Vantage only (Ironclad also excluded — trucking not in its accepted list at this severity/size profile per profile data) | None |
| 05 | MM-01 (scoped class match) + MM-05 (severity ceiling) | Meridian, Coastal Mutual (class), Palmetto (severity ceiling, class scope mismatch) | Ironclad only | None |
| 06 | MM-01/MM-04 (universal class exclusion) + MM-07 | All six carriers | **None — zero matches** | MM-07 diligent-search flag fires regardless |
