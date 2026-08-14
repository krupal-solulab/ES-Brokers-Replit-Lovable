/**
 * Typed calls for /api/es/renewal-remarketing (Backend-AI-OS,
 * verticals/es/workflows/renewal_remarketing/router.py). The seventh E&S
 * workflow — see docs/FE_CONTRACT_renewal_remarketing.md in the backend
 * repo. An orchestration workflow: `initiate-remarket` genuinely
 * re-invokes MarketMatchingPipeline, so a successful call also creates a
 * new item visible at /api/es/market-matching.
 */
import { api } from "./client";
import type { components } from "./schema";

// Qualified with the module path — every ES workflow router defines its own
// `ReviewItemOut`/`RunRequest` classes (see marketMatching.ts's comment).
export type ReviewItemOut =
  components["schemas"]["verticals__es__workflows__renewal_remarketing__router__ReviewItemOut"];
export type RemarketDecisionPayload = components["schemas"]["RemarketDecisionPayload"];
export type ComparisonOutputOut = components["schemas"]["ComparisonOutputOut"];

const BASE = "/api/es/renewal-remarketing";

export function listRenewalRemarketing() {
  return api.get<ReviewItemOut[]>(BASE);
}

export function getRenewalRemarketing(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

export function runRenewalRemarketing(scenarioRef: string) {
  return api.post<ReviewItemOut>(`${BASE}/run`, { scenario_ref: scenarioRef });
}

export interface LiveBind {
  bind_id: string;
  named_insured: string | null;
  carrier_name: string | null;
}

/** Every real Binder Issuance bind for this tenant, for the "Check live
 * renewal" picker. */
export function listLiveBinds() {
  return api.get<LiveBind[]>(`${BASE}/live-binds`);
}

/** Additive alongside the fixture-scenario run above: a real trigger-stage
 * review built from an ACTUAL Binder Issuance bind + real Endorsement
 * Processing history for it — genuine Binder Issuance/Endorsement
 * Processing -> Renewal Remarketing hand-off (FR-2), not another fixture
 * scenario. */
export function runRenewalRemarketingLive(bindId: string) {
  return api.post<ReviewItemOut>(`${BASE}/run-live`, { bind_id: bindId });
}

/** "Approve light check" / "Approve full remarket" — both use this same
 * action. Genuinely re-invokes MarketMatchingPipeline; 409s if the decision
 * was NO_REMARKET. Pass a real messageId (from listLiveInbox) to re-invoke
 * Market Matching against that real message instead of the Workflow_10
 * fixture fallback. */
export function initiateRemarket(itemId: string, messageId?: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/initiate-remarket`, {
    message_id: messageId ?? null,
  });
}

export interface LiveInboxMessage {
  id: string;
  subject: string;
}

/** Real Gmail messages for this item's real named insured — reused for
 * both re-shop-candidate discovery (feeding initiateRemarket's optional
 * messageId) and incumbent-offer discovery (feeding runLiveComparison). */
export function listLiveInbox(itemId: string) {
  return api.get<LiveInboxMessage[]>(`${BASE}/live-inbox?item_id=${encodeURIComponent(itemId)}`);
}

export interface LiveAlternativeQuote {
  quote_comparison_item_id: string;
  carrier_name: string;
  premium: number | null;
  limits: string | null;
}

/** Real, already-selected Quote Comparison items for this item's real
 * named insured — the "alternative" side of the RR-06 comparison. */
export function listLiveAlternativeQuotes(itemId: string) {
  return api.get<LiveAlternativeQuote[]>(
    `${BASE}/live-alternative-quotes?item_id=${encodeURIComponent(itemId)}`,
  );
}

/** RR-06, live: a real incumbent-offer email against a real, already-
 * selected Quote Comparison quote. Creates a NEW review item (the
 * comparison stage), same as the fixture's own Scenario 05 being a
 * separate scenario from Scenario 02, not an in-place update. */
export function runLiveComparison(
  itemId: string,
  messageId: string,
  quoteComparisonItemId: string,
) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/run-live-comparison`, {
    message_id: messageId,
    quote_comparison_item_id: quoteComparisonItemId,
  });
}

export function acceptIncumbent(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/accept-incumbent`);
}

export function escalateRenewalRemarketing(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/escalate`);
}

export interface FixtureScenario {
  ref: string;
  label: string;
}

/** The 6 Workflow_16 fixture scenarios (see
 * Data sets/Workflow 7/renewal_remarketing_dataset/README.md). */
export const FIXTURE_SCENARIOS: FixtureScenario[] = [
  { ref: "scenario_01", label: "Continental Freight — flat exposure, no losses (no remarket)" },
  {
    ref: "scenario_02",
    label: "Summit Roofing — 58.5% increase, continued severity (full remarket)",
  },
  {
    ref: "scenario_03",
    label: "Oakwood Apartment Homes — favorable change, larger size band (light check)",
  },
  { ref: "scenario_04", label: "Delta Electric — incumbent silent 25 days out (urgent remarket)" },
  {
    ref: "scenario_05",
    label: "Summit Roofing — post-remarket comparison (exception-quote flagging)",
  },
  {
    ref: "scenario_06",
    label: "Clearpath Bookkeeping — remarketing history shows no value (no remarket)",
  },
];
