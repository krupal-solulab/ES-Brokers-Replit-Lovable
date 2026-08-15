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

/** PR-03 (time-to-placement) — hand-defined; not yet in generated schema.ts.
 * `avg_days` is RAW elapsed time (submission matched -> bound).
 * `delay_excluded` is true when carrier-attributed figures are also available
 * (see `TimeToPlacementCarrierAttributedOut`). */
export interface TimeToPlacementOut {
  carrier_name: string;
  submissions_bound: number;
  avg_days: number;
  low_volume_flag: boolean;
  delay_excluded: boolean;
}

/** FR-4 (carrier-attributed time-to-placement) — hand-defined; not yet in
 * generated schema.ts.  `avg_days_raw` equals `TimeToPlacementOut.avg_days`;
 * `avg_days_carrier_attributed` is raw minus completed BROKER/AGENT
 * PipelineStageEvent spans.  Present only when stage events exist. */
export interface TimeToPlacementCarrierAttributedOut {
  carrier_name: string;
  submissions_bound: number;
  avg_days_raw: number;
  avg_days_carrier_attributed: number;
  low_volume_flag: boolean;
  delay_excluded: boolean;
}

/** FR-6 / PR-04 (revenue attribution) — always provisional.
 * `not_configured` is true when no commission rate exists for this carrier.
 * `estimated_commission` is null when not_configured. */
export interface RevenueAttributionOut {
  carrier_name: string;
  submissions_bound: number;
  bound_premium_total: number | null;
  commission_rate: number | null;
  estimated_commission: number | null;
  not_configured: boolean;
  provisional: boolean;
}

export type PipelineReportPayload = components["schemas"]["PipelineReportPayload"] & {
  time_to_placement: TimeToPlacementOut[];
  time_to_placement_carrier_attributed: TimeToPlacementCarrierAttributedOut[];
  revenue_attribution: RevenueAttributionOut[];
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
