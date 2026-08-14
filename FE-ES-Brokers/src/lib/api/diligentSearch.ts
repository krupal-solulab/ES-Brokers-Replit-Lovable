/**
 * Typed calls for /api/es/diligent-search (Backend-AI-OS,
 * verticals/es/workflows/diligent_search/router.py). The eighth E&S
 * workflow — see docs/FE_CONTRACT_diligent_search.md in the backend repo.
 * The highest legal-stakes workflow in the vertical: a document is only
 * ever generated on a confirmed SUFFICIENT determination, never partially.
 */
import { api } from "./client";
import type { components } from "./schema";

// Qualified with the module path — every ES workflow router defines its own
// `ReviewItemOut`/`RunRequest` classes (see marketMatching.ts's comment).
export type ReviewItemOut =
  components["schemas"]["verticals__es__workflows__diligent_search__router__ReviewItemOut"];
export type ComplianceRecordPayload = components["schemas"]["ComplianceRecordPayload"];
export type StateDeterminationOut = components["schemas"]["StateDeterminationOut"];

const BASE = "/api/es/diligent-search";

export function listDiligentSearch() {
  return api.get<ReviewItemOut[]>(BASE);
}

export function getDiligentSearch(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

export function runDiligentSearch(scenarioRef: string) {
  return api.post<ReviewItemOut>(`${BASE}/run`, { scenario_ref: scenarioRef });
}

export function approveDiligentSearch(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/approve`);
}

/** Escalates an ambiguous PENDING_DETERMINATION state to compliance/legal (FR-7). */
export function escalateDiligentSearch(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/escalate`);
}

export interface LiveStubSubmission {
  item_id: string;
  submission_id: string | null;
}

/** Real submissions Market Matching's MM-07 has already flagged (a real,
 * linked stub review item exists) but no broker has completed a real
 * search for yet. No named_insured is available here — Market Matching's
 * real payload never carries one — so these are shown by submission_id. */
export function listLiveSubmissions() {
  return api.get<LiveStubSubmission[]>(`${BASE}/live-submissions`);
}

export interface LiveDeclinationInput {
  carrier: string;
  date: string | null;
  written_evidence: boolean;
}

export interface LiveStateInput {
  state: string;
  status: "exempt" | "required" | "pending";
  export_list_note?: string | null;
  admitted_declinations_required?: number | null;
  declinations: LiveDeclinationInput[];
}

/** Runs a real per-state determination from broker/compliance-supplied
 * facts and declination records for a real MM-07-seeded submission —
 * updates that SAME review item in place. The strict DS-01..DS-04
 * sufficiency/generation gate on the backend is unchanged; this only
 * supplies real inputs a human actually knows, never a shortcut around it. */
export function runLiveDiligentSearch(
  itemId: string,
  body: { submission_id?: string | null; named_insured?: string | null; states: LiveStateInput[] },
) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/run-live`, body);
}

export interface FixtureScenario {
  ref: string;
  label: string;
}

/** The 4 Workflow_17 fixture scenarios (see
 * Data sets/Workflow 8/diligent_search_dataset/README.md). */
export const FIXTURE_SCENARIOS: FixtureScenario[] = [
  { ref: "scenario_01", label: "GreenLeaf Cultivation (Oregon) — ready, 3/3 written declinations" },
  { ref: "scenario_02", label: "Ridgeline Amusement Park (Texas) — export-list exemption" },
  { ref: "scenario_03", label: "Pinecrest Demolition (Florida) — blocked, verbal-only decline" },
  { ref: "scenario_04", label: "Continental Freight (8-state) — partial, multi-state checklist" },
];
