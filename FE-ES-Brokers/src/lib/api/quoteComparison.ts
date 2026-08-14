/**
 * Typed calls for /api/es/quote-comparison (Backend-AI-OS,
 * verticals/es/workflows/quote_comparison/router.py). The fourth E&S
 * workflow — see docs/FE_CONTRACT_quote_comparison.md in the backend repo.
 */
import { api } from "./client";
import type { components } from "./schema";

// Qualified with the module path — every ES workflow router defines its own
// `ReviewItemOut`/`RunRequest` classes (see marketMatching.ts's comment).
// `SubjectivityOut` needs the same treatment as of Workflow 5 — binder_issuance
// defines its own class with the same name.
export type ReviewItemOut =
  components["schemas"]["verticals__es__workflows__quote_comparison__router__ReviewItemOut"];
export type ComparisonPayload = components["schemas"]["ComparisonPayload"];
export type ExtractedQuoteOut = components["schemas"]["ExtractedQuoteOut"];
export type SubjectivityOut =
  components["schemas"]["verticals__es__workflows__quote_comparison__schema__SubjectivityOut"];
export type UrgencyFlagOut = components["schemas"]["UrgencyFlagOut"];

const BASE = "/api/es/quote-comparison";

export function listQuoteComparison() {
  return api.get<ReviewItemOut[]>(BASE);
}

/** Urgency (`output_mode`/`urgency_flags`) is recomputed against today's real
 * date server-side on every call — re-fetch to get current urgency, no /run
 * re-trigger needed. */
export function getQuoteComparison(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

export function runQuoteComparison(scenarioRef: string) {
  return api.post<ReviewItemOut>(`${BASE}/run`, { scenario_ref: scenarioRef });
}

/** The one and only trigger for the Agent Communication hand-off (FR-20) —
 * fires a real QUOTE_TERMS_SUMMARY draft server-side, no navigation needed. */
export function selectQuote(itemId: string, quoteId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/select/${quoteId}`);
}

export function requestRevisedTerms(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/request-revised-terms`);
}

export function markLapsed(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/mark-lapsed`);
}

export interface LiveInboxMessage {
  id: string;
  subject: string;
}

/** Real Gmail messages that could be a carrier response for this real
 * submission — matched server-side by the submission's own real named
 * insured, never the whole inbox. Requires Gmail connected + backend
 * CONNECTORS_MODE=live. */
export function listLiveInbox(submissionId: string) {
  return api.get<LiveInboxMessage[]>(
    `${BASE}/live-inbox?submission_id=${encodeURIComponent(submissionId)}`,
  );
}

/** Persists the picked real carrier-response email and re-runs the
 * comparison against every real response accumulated so far for this
 * submission (FR-3) — not just the latest one. */
export function runQuoteComparisonLive(submissionId: string, messageId: string) {
  return api.post<ReviewItemOut>(`${BASE}/run-live`, {
    submission_id: submissionId,
    message_id: messageId,
  });
}

export interface FixtureScenario {
  ref: string;
  label: string;
}

/** The 6 Workflow_13 fixture scenarios (see
 * Data sets/Workflow 4/quote_comparison_dataset/README.md). */
export const FIXTURE_SCENARIOS: FixtureScenario[] = [
  { ref: "scenario_01", label: "Delta Electric — Ironclad + Meridian (contingent secondary)" },
  { ref: "scenario_02", label: "Oakwood Apartment Homes — deductible trade-off" },
  { ref: "scenario_03", label: "Summit Roofing — late declination + narrow validity" },
  {
    ref: "scenario_04",
    label: "Oakwood Apartment Homes (revised) — timeline-critical subjectivity",
  },
  { ref: "scenario_05", label: "Brightline Facilities Group — price vs. coverage trade-off" },
  { ref: "scenario_06", label: "Continental Freight Carriers — single quote, expiring" },
];
