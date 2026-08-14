# Sample Test Dataset — Binder & Policy Issuance Coordination

6 scenarios covering the full post-quote-selection lifecycle: bind
request → carrier confirmation → ongoing subjectivity tracking → policy
issuance monitoring → final policy reconciliation. Reuses named insureds
and carrier profiles from earlier datasets in this vertical for
continuity.

| # | Scenario | Test Purpose | Expected Outcome |
|---|---|---|---|
| 01 | Continental Freight → Vantage | Clean bind, all subjectivities pre-cleared, carrier confirmation matches exactly | Clean bind, Placement Confirmation fires |
| 02 | Oakwood Apartment Homes → Coastal Mutual | Material pre-bind subjectivity (inspection) not yet cleared | **BLOCKED** — bind order cannot be sent |
| 03 | Delta Electric → Ironclad | Carrier's bind confirmation doesn't match requested terms (deductible + effective date) | **DISCREPANCY FLAGGED** — the single most important test case in this set |
| 04 | Summit Roofing → Ironclad | Post-bind ongoing obligation (loss control report due in 60 days) — must NOT block the bind | Clean bind + tracked ongoing task |
| 05 | Clearpath Bookkeeping → Apex Excess Lines | Policy documents overdue against carrier's own stated issuance timeline | Proactive overdue alert |
| 06 | Oakwood Apartment Homes → Coastal Mutual (later) | Issued policy document doesn't match bound terms (wind/hail deductible doubled) | **MATERIAL DISCREPANCY** — highest-value check in the whole workflow |

## The two things this dataset is most focused on

1. **A carrier's own confirmation is data to verify, not ground truth
   to trust automatically.** Scenarios 03 and 06 both exist to make the
   same point at two different stages of the lifecycle (bind
   confirmation and final policy issuance): carriers make processing
   errors, and a system that treats every carrier-issued document as
   automatically correct will propagate those errors straight through
   to the retail agent and, ultimately, the insured. This is arguably
   the single highest-value capability in this entire workflow — it's
   the kind of quiet, unglamorous check that prevents a real, costly
   error rather than just saving time.
2. **The same type of subjectivity gets different treatment depending
   on lifecycle timing.** Scenarios 02 and 04 both involve a
   loss-control-related requirement, but one blocks the bind
   (pre-bind, material) and the other doesn't (post-bind, ongoing).
   This is a direct extension of the routine-vs-material distinction
   established in Quote Comparison's QC-02, now split further by
   *when* in the lifecycle the requirement applies — getting this
   distinction wrong in either direction either blocks binds that
   shouldn't be blocked or silently loses track of real ongoing
   carrier obligations.

## Suggested use

Run each scenario through the coordination pipeline and check: (1)
whether pre-bind blocking logic correctly gates the bind order (Scenario
02), (2) whether carrier confirmations and issued policies are actively
reconciled against what was actually requested/bound rather than
accepted at face value (Scenarios 03, 06), and (3) whether downstream
triggers to Retail Agent Communication only fire on genuinely clean,
verified outcomes — Scenarios 03 and 06 should both suppress the
Placement Confirmation / policy-delivered trigger until their respective
discrepancies are resolved.
