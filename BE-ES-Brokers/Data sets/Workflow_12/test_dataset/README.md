# Sample Test Dataset — Retail Agent Communication Copilot

6 trigger scenarios, structurally similar to the MGA Broker Communication
dataset — inputs are structured output objects from upstream workflows
(Market Matching, Package Assembly), not raw documents, since this
workflow's job is drafting communication from data those workflows
already produced.

| # | Trigger | Communication Type | Key Test Focus |
|---|---|---|---|
| 01 | Delta Electric (submitted to 2 carriers) | Submission Acknowledgment | Baseline — concrete status update, sets timing expectation |
| 02 | Delta Electric (Palmetto BLOCKED) | Missing Info Request (carrier-specific) | Must scope the ask to the correct carrier when multiple placements are in flight simultaneously |
| 03 | GreenLeaf Cultivation (zero-match) | No Market Found Notice | **Highest-sensitivity draft in the set** — mirrors the MGA Non-Renewal Notice's "our constraint, not your account" framing, plus a genuinely new compliance question about carrier-name disclosure |
| 04 | Oakwood Apartment Homes (bound) | Placement Confirmation | Clean good-news case — contrast against Trigger 06 |
| 05 | Delta Electric (no response, 9 days) | No-Response Follow-up | Tests honest urgency calibration — wholesale acceptance windows are often longer than MGA deadlines, and the tone should reflect that rather than manufacturing false urgency |
| 06 | Summit Roofing Group (quote received) | Quote/Terms Summary with pricing justification | **Second-hardest draft in the set** — good news (a bindable quote) that still needs to justify a high price without reading as either an apology or a sales pitch |

## What's genuinely new here compared to the MGA Broker Communication dataset

- **No Market Found (Trigger 03) is a new communication type with no
  direct MGA equivalent.** The closest analog is the MGA Non-Renewal
  Notice, but the underlying situation is different — this is about
  failing to place *new* business rather than withdrawing *existing*
  coverage, and it raises a compliance question (can carrier-level
  declination detail be disclosed?) that doesn't have an MGA-side
  parallel. This draft is explicitly marked in its trigger data as
  needing a compliance decision before the product can safely default
  to either full disclosure or aggregate-only framing.
- **Quote/Terms Summary with pricing justification (Trigger 06) is a
  harder version of the MGA Quote Summary.** In the MGA dataset, a
  clean PROCEED case and a quote summary were essentially the same easy
  case. In wholesale/E&S, a bindable quote can still carry a genuinely
  high price relative to a clean account, and the agent needs the "why"
  clearly connected to specific loss history — omitting that context
  risks the agent (and their client) assuming the wholesaler is padding
  margin rather than passing through real market pricing.
- **Urgency calibration is directionally different.** The MGA dataset's
  No-Response Follow-up anchored urgency to a tight effective-date
  deadline. Trigger 05 here deliberately tests the opposite calibration
  — Palmetto's 45-day acceptance window means genuine urgency is often
  lower in this vertical, and the draft should say so honestly rather
  than defaulting to the same urgency register as the MGA version.

## Suggested use

Same evaluation approach as the MGA Broker Communication dataset: feed
each `trigger_input.json` into the drafting pipeline, compare against
`expected_draft.txt` on both factual completeness and tone (per each
scenario's `tone_notes.txt`). Pay particular attention to Triggers 03 and
06 — these are the two drafts with real relationship and (for 03)
compliance stakes, and the best test of whether tone calibration is
actually carrier/situation-aware rather than producing generically
polite text regardless of context.
