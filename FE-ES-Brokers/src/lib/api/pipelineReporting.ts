/**
 * Typed calls for /api/es/pipeline-reporting (Backend-AI-OS,
 * verticals/es/workflows/pipeline_reporting/router.py). The 10th and last
 * workflow on the original E&S roadmap — see
 * docs/FE_CONTRACT_pipeline_reporting.md in the backend repo.
 *
 * Pure aggregation/reporting: only run/list/detail, no approve/escalate —
 * a report isn't a determination a human approves or declines.
 */
import { api } from "./client";
import type { components } from "./schema";

/** PR-03 (time-to-placement) — added after schema.ts was last generated, so
 * hand-defined here rather than pulled from `components["schemas"]`.
 * `avg_days` is RAW elapsed time (submission matched -> bound);
 * `delay_excluded` is always false today — FR-4's broker/agent-side delay
 * exclusion isn't computed anywhere (Package Assembly has no history of
 * when a submission entered/left BLOCKED status to measure it from). */
export interface TimeToPlacementOut {
  carrier_name: string;
  submissions_bound: number;
  avg_days: number;
  low_volume_flag: boolean;
  delay_excluded: boolean;
}

export type PipelineReportPayload = components["schemas"]["PipelineReportPayload"] & {
  time_to_placement: TimeToPlacementOut[];
};

// Qualified with the module path — every ES workflow router defines its own
// `ReviewItemOut`/`RunRequest` classes (see marketMatching.ts's comment).
// Overrides the generated `payload` field with the extended type above.
export type ReviewItemOut = Omit<
  components["schemas"]["verticals__es__workflows__pipeline_reporting__router__ReviewItemOut"],
  "payload"
> & { payload?: PipelineReportPayload | null };
export type FunnelStageOut = components["schemas"]["FunnelStageOut"];
export type CarrierPerformanceOut = components["schemas"]["CarrierPerformanceOut"];
export type RemarketOutcomeOut = components["schemas"]["RemarketOutcomeOut"];

const BASE = "/api/es/pipeline-reporting";

export function listPipelineReporting() {
  return api.get<ReviewItemOut[]>(BASE);
}

export function getPipelineReporting(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

export function runPipelineReporting(scenarioRef: string) {
  return api.post<ReviewItemOut>(`${BASE}/run`, { scenario_ref: scenarioRef });
}

/** Additive alongside the fixture-scenario run above: builds one report
 * from real cross-workflow data already logged for this tenant (Market
 * Matching, Package Assembly, Quote Comparison, Binder Issuance, Renewal
 * Remarketing) — genuine aggregation, not another fixture scenario. */
export function runPipelineReportingLive() {
  return api.post<ReviewItemOut>(`${BASE}/run-live`);
}

export interface FixtureScenario {
  ref: string;
  label: string;
}

/** The 4 Workflow_19 fixture scenarios (see
 * Data sets/Workflow 10/pipeline_reporting_dataset/README.md). */
export const FIXTURE_SCENARIOS: FixtureScenario[] = [
  { ref: "scenario_01", label: "Q3 clean funnel — complete data baseline" },
  { ref: "scenario_02", label: "Carrier hit-rate — one low-volume carrier" },
  { ref: "scenario_03", label: "Q3 funnel with a 2-week logging gap (release gate)" },
  { ref: "scenario_04", label: "Remarketing value — $0-savings, confirmed-incumbent case" },
];
