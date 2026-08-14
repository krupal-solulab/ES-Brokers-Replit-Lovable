# Sample Test Dataset — Diligent Search & Compliance Documentation

4 scenarios covering the range of determinations this workflow must
make correctly: standard requirement met, export-list exemption,
insufficient evidence, and multi-state complexity.

| # | Scenario | Test Purpose | Expected Status |
|---|---|---|---|
| 01 | GreenLeaf Cultivation (Oregon) | Standard case, 3 written declinations on file | READY — compliant document generated |
| 02 | Ridgeline Amusement Park (Texas) | Export-list exemption applies | EXEMPT — must be logged distinctly from "missing" |
| 03 | Pinecrest Demolition (Florida) | Only 2 of 3 declinations, one verbal-only | BLOCKED — cannot generate document |
| 04 | Continental Freight (8-state risk) | Different requirements per state, some unchecked | PARTIAL — state-by-state, not a single verdict |

## The two things this dataset is built to catch

1. **"No diligent search on file" and "diligent search not required"
   must never look the same in the system.** Scenario 02 exists
   specifically to test this — an export-list exemption produces the
   same *absence of an affidavit* as a missing, non-compliant case
   would, and conflating the two is a real regulatory risk in the
   direction of under-documentation appearing later during an audit.
2. **A verbal declination is not written evidence.** Scenario 03 tests
   that the system holds a strict evidentiary bar — generating an
   affidavit that overstates the documented evidence on file is not a
   quality issue, it's a potentially fraudulent document, and the
   system must block rather than paper over the gap.

## Suggested use

Run each scenario through the pipeline and confirm: (1) exemption vs.
requirement is correctly distinguished and explicitly logged either
way, (2) evidence sufficiency checking is strict about written vs.
verbal declinations, and (3) multi-state submissions produce a
state-by-state checklist rather than a single collapsed status.
