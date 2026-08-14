/**
 * Typed calls for /api/es/binder-issuance (Backend-AI-OS,
 * verticals/es/workflows/binder_issuance/router.py). The fifth E&S
 * workflow — see docs/FE_CONTRACT_binder_issuance.md in the backend repo.
 */
import { api } from "./client";
import type { components } from "./schema";

// Qualified with the module path — every ES workflow router defines its own
// `ReviewItemOut`/`RunRequest` classes (see marketMatching.ts's comment).
// `DiscrepancyOut` needs the same treatment as of Workflow 6 — endorsement
// defines its own class with the same name.
export type ReviewItemOut =
  components["schemas"]["verticals__es__workflows__binder_issuance__router__ReviewItemOut"];
export type BindCoordinationPayload = components["schemas"]["BindCoordinationPayload"];
export type DiscrepancyOut =
  components["schemas"]["verticals__es__workflows__binder_issuance__schema__DiscrepancyOut"];
export type OngoingObligationOut = components["schemas"]["OngoingObligationOut"];
export type DiscrepancyResolution = "accept_carrier_version" | "flag_carrier_error";
export type PolicyDiscrepancyResolution = "accept_issued_version" | "flag_carrier_error";

const BASE = "/api/es/binder-issuance";

export function listBinderIssuance() {
  return api.get<ReviewItemOut[]>(BASE);
}

/** Issuance-overdue status and obligation reminders are recomputed against
 * today's real date server-side on every call. */
export function getBinderIssuance(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

export function runBinderIssuance(scenarioRef: string) {
  return api.post<ReviewItemOut>(`${BASE}/run`, { scenario_ref: scenarioRef });
}

/** Additive alongside the fixture-scenario run above: starts a real
 * pre-bind pass from an actual, already-selected Quote Comparison item's
 * real terms — genuine Quote Comparison -> Binder Issuance hand-off, not
 * another fixture scenario. */
export function runBinderIssuanceFromQuote(quoteComparisonItemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/run-from-quote-comparison`, {
    quote_comparison_item_id: quoteComparisonItemId,
  });
}

/** Required before Placement Confirmation can fire (BI-06's gate). */
export function resolveConfirmationDiscrepancy(itemId: string, resolution: DiscrepancyResolution) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/resolve-confirmation-discrepancy`, {
    resolution,
  });
}

/** Required before Policy Documents Delivered can fire (BI-06's gate). */
export function resolvePolicyDiscrepancy(itemId: string, resolution: PolicyDiscrepancyResolution) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/resolve-policy-discrepancy`, { resolution });
}

export function escalateBinderIssuance(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/escalate`);
}

export interface LiveInboxMessage {
  id: string;
  subject: string;
}

/** Real Gmail messages that could be this bind's carrier confirmation OR
 * its eventual issued policy — matched server-side by the bind's own real
 * named insured. Requires Gmail connected + backend CONNECTORS_MODE=live. */
export function listLiveInbox(itemId: string) {
  return api.get<LiveInboxMessage[]>(`${BASE}/live-inbox?item_id=${encodeURIComponent(itemId)}`);
}

/** Attaches a real carrier bind-confirmation email — advances READY -> SENT
 * and runs BI-03 reconciliation for real. */
export function attachLiveConfirmation(itemId: string, messageId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/attach-live-confirmation`, {
    message_id: messageId,
  });
}

/** Attaches a real issued-policy document — runs BI-05 reconciliation
 * against the confirmed bind terms. */
export function attachLiveIssuedPolicy(itemId: string, messageId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/attach-live-policy`, {
    message_id: messageId,
  });
}

/** Marks a real pre-bind subjectivity resolved (broker confirms the
 * underlying condition was actually satisfied) and re-runs BI-02's blocking
 * check — the only way to unblock a bind stuck on a material, unresolved
 * subjectivity. Matched by exact description text. */
export function clearSubjectivity(itemId: string, description: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/clear-subjectivity`, {
    description,
  });
}

export interface FixtureScenario {
  ref: string;
  label: string;
}

/** The 6 Workflow_14 fixture scenarios (see
 * Data sets/Workflow 5/binder_issuance_dataset/README.md). */
export const FIXTURE_SCENARIOS: FixtureScenario[] = [
  { ref: "scenario_01", label: "Continental Freight → Vantage — clean bind" },
  { ref: "scenario_02", label: "Oakwood Apartment Homes → Coastal Mutual — blocked (inspection)" },
  { ref: "scenario_03", label: "Delta Electric → Ironclad — bind confirmation discrepancy" },
  { ref: "scenario_04", label: "Summit Roofing → Ironclad — clean bind + ongoing obligation" },
  { ref: "scenario_05", label: "Clearpath Bookkeeping → Apex Excess Lines — overdue issuance" },
  {
    ref: "scenario_06",
    label: "Oakwood Apartment Homes → Coastal Mutual (later) — issued-policy discrepancy",
  },
];
