/**
 * Typed calls for /api/es/market-matching (Backend-AI-OS,
 * verticals/es/workflows/market_matching/router.py). The only workflow with
 * a live backend counterpart today — see AGENTS discovery notes.
 */
import { api } from "./client";
import type { components } from "./schema";

// FastAPI qualifies this with the module path once a second workflow router also
// defines a `ReviewItemOut`/`RunRequest` class (see packageAssembly.ts) — plain
// "ReviewItemOut" no longer exists in the generated schema.
export type ReviewItemOut =
  components["schemas"]["verticals__es__workflows__market_matching__router__ReviewItemOut"];
export type MarketMatchingPayload = components["schemas"]["MarketMatchingPayload"];
export type CarrierMatchOut = components["schemas"]["CarrierMatchOut"];
export type ExcludedCarrierOut = components["schemas"]["ExcludedCarrierOut"];
export type DiligentSearchOut = components["schemas"]["DiligentSearchOut"];
export type DocumentOut = components["schemas"]["DocumentOut"];
export type ReviewActionVerb = "approve" | "override" | "escalate" | "send" | "issue";

const BASE = "/api/es/market-matching";

/** The Workflow_10 fixture set this backend has real data for (see
 * Backend-AI-OS docs/DATA_AND_FIXTURES.md) — there is no submission-upload
 * endpoint yet, so this is the closed set of refs `run()` can be called with. */
export const FIXTURE_SUBMISSION_REFS = [
  "submission_01",
  "submission_02",
  "submission_03",
  "submission_04",
  "submission_05",
  "submission_06",
] as const;

export function listMarketMatching() {
  return api.get<ReviewItemOut[]>(BASE);
}

export function getMarketMatching(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

export function listDocuments(itemId: string) {
  return api.get<DocumentOut[]>(`${BASE}/${itemId}/documents`);
}

export function runMarketMatching(submissionRef: string) {
  return api.post<ReviewItemOut>(`${BASE}/run`, { submission_ref: submissionRef });
}

export function actOnMarketMatching(itemId: string, action: ReviewActionVerb) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/${action}`);
}

export interface LiveInboxMessage {
  id: string;
  subject: string;
}

/** Real Gmail messages via the tenant's connected Nango integration (Settings ->
 * Integrations) — requires CONNECTORS_MODE=live on the backend. Picking one and
 * calling `runMarketMatching(message.id)` runs the real pipeline against a real
 * email instead of a Workflow_10 fixture. */
export function listLiveInbox() {
  return api.get<LiveInboxMessage[]>(`${BASE}/live-inbox`);
}
