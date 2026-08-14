/**
 * Typed calls for /api/es/carrier-appetite-intelligence (Backend-AI-OS,
 * verticals/es/workflows/carrier_appetite_intelligence/router.py). The
 * ninth and last E&S workflow in Phase 3 — see
 * docs/FE_CONTRACT_carrier_appetite_intelligence.md in the backend repo.
 *
 * No mutable Carrier Appetite Profile store exists anywhere in the
 * backend — `metadata_refresh`/`suggested_action` are computed and
 * recorded here, never applied to any real profile. This workflow should
 * be quiet almost all the time: most evaluations come back SUPPRESSED.
 */
import { api } from "./client";
import type { components } from "./schema";

// Qualified with the module path — every ES workflow router defines its own
// `ReviewItemOut`/`RunRequest` classes (see marketMatching.ts's comment).
export type ReviewItemOut =
  components["schemas"]["verticals__es__workflows__carrier_appetite_intelligence__router__ReviewItemOut"];
export type CarrierAppetiteEvaluationPayload =
  components["schemas"]["CarrierAppetiteEvaluationPayload"];
export type EvidenceItemOut = components["schemas"]["EvidenceItemOut"];

const BASE = "/api/es/carrier-appetite-intelligence";

export function listCarrierAppetiteIntelligence() {
  return api.get<ReviewItemOut[]>(BASE);
}

export function getCarrierAppetiteIntelligence(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

export function runCarrierAppetiteIntelligence(scenarioRef: string) {
  return api.post<ReviewItemOut>(`${BASE}/run`, { scenario_ref: scenarioRef });
}

/** Additive alongside the fixture-scenario run above: evaluates every
 * carrier with a real, classifiable declination signal already logged by
 * Quote Comparison for this tenant — genuine cross-workflow aggregation,
 * not another fixture scenario. */
export function runCarrierAppetiteIntelligenceLive() {
  return api.post<ReviewItemOut[]>(`${BASE}/run-live`);
}

/** Approving a GENUINE_INCONSISTENCY suggestion — records approval only,
 * never changes any profile data (none exists to change). */
export function approveCarrierAppetiteIntelligence(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/approve`);
}

export function dismissCarrierAppetiteIntelligence(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/dismiss`);
}

export interface FixtureScenario {
  ref: string;
  label: string;
}

/** The 4 Workflow_18 fixture scenarios (see
 * Data sets/Workflow 9/carrier_intelligence_dataset/README.md). */
export const FIXTURE_SCENARIOS: FixtureScenario[] = [
  { ref: "scenario_01", label: "Palmetto / Roofing — 1 data point (suppressed, low volume)" },
  {
    ref: "scenario_02",
    label: "Meridian / Landscaping — genuine class-level pattern (suggestion)",
  },
  { ref: "scenario_03", label: "Ironclad / Roofing — account-specific decline (suppressed)" },
  {
    ref: "scenario_04",
    label: "Coastal Mutual / Habitational — 4/4 consistent (metadata refresh)",
  },
];
