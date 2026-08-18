# Sample Test Dataset — Submission Package Assembly

6 scenarios, each starting from a Market Matching output (broker has
already selected which carrier(s) to approach) and testing what a
correctly-assembled, carrier-specific submission package should contain.
Reuses named insureds and carrier profiles from the Market Matching
dataset for continuity — this workflow is a direct downstream consumer
of that one.

| # | Scenario | Test Purpose | Expected Status |
|---|---|---|---|
| 01 | Continental Freight → Vantage Excess Partners | Clean case with one document type (actuarial projection) that genuinely cannot be sourced from extraction | **READY WITH ONE GAP** — tests that the system distinguishes "we can't get this" from "broker forgot this" |
| 02 | Delta Electric → Palmetto Specialty | Two blocking gaps: incomplete loss run + non-auto-fillable supplemental | **BLOCKED** — tests that the system never presents an incomplete package as ready |
| 03 | Delta Electric → Ironclad AND Meridian (simultaneous) | Same submission, two carriers with different requirements | **Two genuinely different packages** — the loss-run-length issue appears in one package and not the other, based on each carrier's own stated requirement |
| 04 | Oakwood Apartment Homes → Coastal Mutual | Supplemental form with a field carrier metadata calls "auto-fillable" but that requires inference, not direct extraction | **READY, with one field correctly left for manual entry** — tests that grounding constraints override a convenience shortcut |
| 05 | Summit Roofing → Ironclad | High-severity risk going to a carrier with known appetite for it — cover letter must proactively frame loss history, not hide it | **READY**, with the hardest tone-adaptation test in the set |
| 06 | Clearpath Bookkeeping → Apex Excess Lines | Clean, simple, low-stakes baseline | **READY** — control case, confirms no over-engineering on simple accounts |

## The two hardest things this dataset tests

1. **Same fact, different treatment per carrier (Scenario 03).** A
   naive implementation generates one cover letter and reuses it across
   carriers with minor find-and-replace. The correct behavior evaluates
   every fact against *each carrier's own stated requirements*
   independently — the same 3-year loss run is a non-issue for Ironclad
   and a blocking gap for Meridian, and the packages must reflect that
   difference, not treat the underlying submission data as producing one
   fixed verdict.
2. **Resisting a plausible-sounding shortcut (Scenario 04).** The
   carrier profile itself suggests a field is "auto-fillable" via
   inference (unit count from TIV), but the grounding requirement
   established across every Coverline workflow says no — only fields
   with a direct, cited source should be auto-populated. This is worth
   testing explicitly because it's the kind of shortcut that looks
   reasonable in isolation and only causes damage once an underwriter
   relies on a subtly wrong inferred number.

## Suggested use

Run each scenario through the assembly pipeline and check three things
separately: (1) is the package status (ready / ready-with-gap / blocked)
correct, (2) does the cover letter draft correctly reflect that specific
carrier's requirements and appetite notes rather than a generic template,
and (3) does every specific claim in the cover letter trace back to a
real extracted or carrier-profile field, per the grounding requirement
called out in Scenario 05's tone notes.
