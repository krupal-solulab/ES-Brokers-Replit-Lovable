# Sample Test Dataset — Endorsement / Mid-Term Change Processing

6 scenarios covering mid-term change requests on already-bound policies,
spanning routine administrative changes through appetite-breaking
requests. Reuses bound accounts established in the Binder & Policy
Issuance dataset for continuity.

| # | Scenario | Test Purpose | Expected Classification |
|---|---|---|---|
| 01 | Continental Freight — add additional insured | Clean routine, no-premium-impact change | **ROUTINE**, fast-track |
| 02 | Summit Roofing — limit increase (2x) | Material change on an account with elevated severity history | **UNDERWRITING-REVIEW-REQUIRED**, premium-bearing |
| 03 | Delta Electric — add new operations class (solar installation) | Class not on carrier's accepted OR excluded list — genuine unknown | **APPETITE UNKNOWN**, must confirm with carrier before processing |
| 04 | Oakwood Apartment Homes — add location | Material change within known appetite, requires pro-rata calc + missing state-licensing clarification | **MATERIAL BUT IN-APPETITE**, pro-rata required |
| 05 | Continental Freight — issued endorsement missing part of request | Carrier partially fulfilled a two-part request | **DISCREPANCY** — reconciliation catch |
| 06 | Clearpath Bookkeeping — headcount update | Small-account control case — percentage change looks large, absolute change is modest | **ROUTINE**, standard pro-rata |

## The three distinctions this dataset is built to test

1. **Routine vs. underwriting-review-required is not just "big change =
   review."** Scenario 04 deliberately sits between Scenario 01's clean
   routine case and Scenario 02's clear underwriting-review case — a
   material change (adding a $12.5M location) that's still within the
   carrier's known appetite gets a different treatment than a material
   change that also touches severity risk on an account with a rocky
   loss history. Materiality and appetite-fit are separate questions,
   and the dataset is built so they don't always point the same
   direction.
2. **An absent class code is not the same as an excluded one.**
   Scenario 03 directly extends the same principle established in
   Market Matching's MM-04 interpretation notes — solar panel
   installation appearing on neither Ironclad's accepted nor excluded
   list must be treated as a genuine unknown requiring carrier
   confirmation, not auto-approved (dangerous) or auto-rejected
   (unnecessarily conservative, and possibly wrong).
3. **Percentage change can be misleading at small scale.** Scenario 06
   is included specifically as a control — a 75% headcount increase
   sounds dramatic by percentage, but on a $2,400-premium account it's
   a minor absolute change. The system should surface both figures
   rather than triggering escalation logic off percentage alone.

## Suggested use

Run each scenario through the classification and processing pipeline
and check: (1) whether routine/review/appetite-unknown classification
matches the expected column, (2) whether premium impact and proration
are correctly flagged as needing carrier confirmation rather than
assumed, and (3) whether Scenario 05's reconciliation check correctly
catches a partial-fulfillment discrepancy the same way Binder & Policy
Issuance's BI-05 catches term mismatches — this workflow inherits that
same "never trust the carrier's issued document by default" discipline.
