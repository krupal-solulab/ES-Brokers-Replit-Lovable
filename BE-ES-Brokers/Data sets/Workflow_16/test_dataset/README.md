# Sample Test Dataset — Renewal Remarketing

6 scenarios covering the full remarket decision spectrum for bound
policies approaching renewal — from clean auto-renewals through
urgent, lapse-risk-driven remarketing. Reuses bound accounts established
across the Binder & Policy Issuance and Endorsement Processing datasets
for continuity.

| # | Scenario | Trigger Reason | Expected Decision |
|---|---|---|---|
| 01 | Continental Freight — flat exposure, no losses | None | **NO REMARKET** — accept incumbent terms |
| 02 | Summit Roofing — 58.5% increase from continued severity | Adverse loss + disproportionate pricing | **FULL REMARKET** — confirm no better alternative exists |
| 03 | Oakwood Apartment Homes — known exposure growth, improving loss trend | Favorable change + larger size band | **LIGHT REMARKET CHECK** — distinct from full shopping |
| 04 | Delta Electric — incumbent hasn't responded, 25 days out | Silent non-response / possible appetite exit | **URGENT REMARKET** — lapse-risk driven, not pricing-driven |
| 05 | Summit Roofing — post-remarket comparison (incumbent vs. exception-based alternative) | N/A — comparison stage | Multi-option, with exception-quote context flagged |
| 06 | Clearpath Bookkeeping — small account, 2-year remarketing history shows no value | None — demonstrated low remarket value | **NO REMARKET** — grounded in this account's own history, not a size heuristic |

## The three trigger *types* this dataset distinguishes

This workflow's most important design decision is that "should we
remarket this?" has more than one legitimate trigger reason, and they
call for different urgency and different framing:

1. **Pricing/severity-driven (Scenario 02):** the incumbent's own
   renewal terms look disproportionate to what changed — worth
   confirming there's nothing better, even if the underlying pricing is
   probably justified.
2. **Opportunity-driven (Scenario 03):** nothing is wrong, but favorable
   change plus a shift in the account's size/profile means a
   lighter-touch check has real expected value — distinct in *degree*
   of effort from a full remarket.
3. **Lapse-risk-driven (Scenario 04):** the incumbent's silence itself
   is the signal, independent of price or exposure — this is closer in
   spirit to a timing/urgency alert than a comparison exercise, and
   should be treated with matching urgency.

A system that only recognizes trigger type 1 will miss real value
(Scenario 03) and real risk (Scenario 04). Scenario 06 is the necessary
counterweight — proof that the system also knows when *not* to trigger,
grounded in real account-specific evidence rather than a blanket
small-account exemption.

## Suggested use

Run each scenario through the decision pipeline and check: (1) whether
the correct trigger type (or no-trigger) is identified, (2) whether
Scenario 03's "light check" is distinguished from Scenario 02's "full
remarket" rather than collapsed into one undifferentiated "remarket:
yes/no" flag, and (3) whether Scenario 06's no-remarket decision is
grounded in the account's own remarketing history rather than a generic
account-size rule — the reasoning trail matters as much as the final
decision here.
