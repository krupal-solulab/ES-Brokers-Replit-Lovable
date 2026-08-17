/**
 * Typed calls for /api/es/package-assembly (Backend-AI-OS,
 * verticals/es/workflows/package_assembly/router.py). The second E&S
 * workflow — see docs/FE_CONTRACT_package_assembly.md in the backend repo.
 */
import { api } from "./client";
import type { components } from "./schema";

// Qualified with the module path because market_matching/router.py defines its
// own `ReviewItemOut`/`RunRequest` class too — see marketMatching.ts's comment.
export type ReviewItemOut =
  components["schemas"]["verticals__es__workflows__package_assembly__router__ReviewItemOut"];
export type PackageAssemblyPayload = components["schemas"]["PackageAssemblyPayload"];
export type DocChecklistItemOut = components["schemas"]["DocChecklistItemOut"];
export type SupplementalFieldOut = components["schemas"]["SupplementalFieldOut"];
export type BlockingItemOut = components["schemas"]["BlockingItemOut"];
export type GapItemOut = components["schemas"]["GapItemOut"];
export type CoverLetterOut = components["schemas"]["CoverLetterOut"];
export type StatusLogEntryOut = components["schemas"]["StatusLogEntryOut"];
export type PackageActionVerb = "approve" | "edit" | "send";

const BASE = "/api/es/package-assembly";

/** Workflow_11 fixture scenarios — each already has a carrier selection baked in
 * (see Data sets/Workflow 2/package_assembly_dataset, scenario_NN/market_matching_output.json).
 * Independent of Market Matching's live submission_01..06 today; the backend's own
 * docs note `scenario_ref` becomes a real Market Matching decision id in production. */
export const FIXTURE_SCENARIO_REFS = [
  "scenario_01",
  "scenario_02",
  "scenario_03",
  "scenario_04",
  "scenario_05",
  "scenario_06",
] as const;

export function listPackageAssembly() {
  return api.get<ReviewItemOut[]>(BASE);
}

export function getPackageAssembly(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

/** Response is always a list, even for a single-carrier scenario — omitting
 * carrierId assembles one independent package per carrier the scenario selected. */
export function runPackageAssembly(scenarioRef: string, carrierId?: string) {
  return api.post<ReviewItemOut[]>(`${BASE}/run`, {
    scenario_ref: scenarioRef,
    ...(carrierId ? { carrier_id: carrierId } : {}),
  });
}

export function actOnPackageAssembly(itemId: string, action: PackageActionVerb) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/${action}`);
}

/**
 * FR-20/FR-21: submit the broker-edited cover-letter body to record the
 * normalized Levenshtein edit distance vs the LLM-generated original.
 * Distinct from ``actOnPackageAssembly(id, "edit")`` because the /edit
 * endpoint now requires the edited body in the request.
 *
 * ``editedBody`` must be non-empty (backend returns 422 otherwise).
 */
export function editPackageAssembly(itemId: string, editedBody: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/edit`, { edited_body: editedBody });
}

/** Additive alongside the fixture-scenario run above: assembles a real
 * package per carrier from an ACTUAL Market Matching review item — genuine
 * Market Matching -> Package Assembly hand-off, not another fixture
 * scenario. Omitting carrierId assembles one independent package per
 * carrier the real submission matched. */
export function runPackageAssemblyFromMarketMatching(
  marketMatchingReviewItemId: string,
  carrierId?: string,
  carrierIds?: string[],
) {
  return api.post<ReviewItemOut[]>(`${BASE}/run-from-market-matching`, {
    market_matching_review_item_id: marketMatchingReviewItemId,
    ...(carrierId ? { carrier_id: carrierId } : {}),
    // FR-13 Send handoff: the broker's explicit shortlist — the backend writes
    // a human audit entry (who/when/submission/carriers) and assembles exactly
    // these carriers. Nothing is emailed to any carrier by this call.
    ...(carrierIds && carrierIds.length > 0 ? { carrier_ids: carrierIds } : {}),
  });
}
