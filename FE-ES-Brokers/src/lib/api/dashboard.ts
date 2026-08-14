/**
 * Typed calls for /api/core/dashboard (Backend-AI-OS, core/dashboard/router.py).
 * Every field here is real, computed from live cross-workflow data — no
 * fixtures, no example numbers.
 */
import { api } from "./client";

export interface FunnelStage {
  stage: string;
  count: number | null;
  pctOfPriorStage: number | null;
}

export interface DataGap {
  stage: string;
  reason: string;
}

export interface Funnel {
  stages: FunnelStage[];
  gaps: DataGap[];
  overallConversionPct: number | null;
}

export interface CarrierPerformance {
  carrierName: string;
  submissionsApproached: number;
  quoteRate: number;
  bindRate: number;
  overallHitRate: number;
  lowVolumeFlag: boolean;
}

export interface TimeToPlacement {
  carrierName: string;
  submissionsBound: number;
  avgDays: number;
  lowVolumeFlag: boolean;
}

export interface RemarketOutcome {
  account: string;
  triggerLevel: string;
  outcomeType: string;
  savingsAmount: number | null;
  note: string | null;
}

export interface RecentActivityItem {
  workflow: string;
  ref: string;
  status: string;
  createdAt: string;
}

export interface RemarketPipelineItem {
  namedInsured: string | null;
  incumbentCarrierName: string | null;
  triggerLevel: string | null;
  createdAt: string;
}

export interface DiligentSearchAlert {
  submissionId: string | null;
  onFile: number | null;
  note: string | null;
}

export interface DailyPipelinePoint {
  date: string;
  submissions: number;
  bound: number;
}

export interface DashboardOverview {
  generatedAt: string;
  workflowCounts: Record<string, number>;
  submissionsToday: number;
  quotesReceivedToday: number;
  remarketPending: number;
  endorsementPending: number;
  bindersConfirmed: number;
  boundPremiumMtd: number;
  funnel: Funnel;
  carrierPerformance: CarrierPerformance[];
  timeToPlacement: TimeToPlacement[];
  remarketValue: RemarketOutcome[];
  recentActivity: RecentActivityItem[];
  remarketPipeline: RemarketPipelineItem[];
  diligentSearchAlerts: DiligentSearchAlert[];
  dailyPipeline: DailyPipelinePoint[];
}

interface DashboardOverviewWire {
  generated_at: string;
  workflow_counts: Record<string, number>;
  submissions_today: number;
  quotes_received_today: number;
  remarket_pending: number;
  endorsement_pending: number;
  binders_confirmed: number;
  bound_premium_mtd: number;
  funnel: {
    stages: { stage: string; count: number | null; pct_of_prior_stage: number | null }[];
    gaps: { stage: string; reason: string }[];
    overall_conversion_pct: number | null;
  };
  carrier_performance: {
    carrier_name: string;
    submissions_approached: number;
    quote_rate: number;
    bind_rate: number;
    overall_hit_rate: number;
    low_volume_flag: boolean;
  }[];
  time_to_placement: {
    carrier_name: string;
    submissions_bound: number;
    avg_days: number;
    low_volume_flag: boolean;
  }[];
  remarket_value: {
    account: string;
    trigger_level: string;
    outcome_type: string;
    savings_amount: number | null;
    note: string | null;
  }[];
  recent_activity: { workflow: string; ref: string; status: string; created_at: string }[];
  remarket_pipeline: {
    named_insured: string | null;
    incumbent_carrier_name: string | null;
    trigger_level: string | null;
    created_at: string;
  }[];
  diligent_search_alerts: {
    submission_id: string | null;
    on_file: number | null;
    note: string | null;
  }[];
  daily_pipeline: { date: string; submissions: number; bound: number }[];
}

export async function getDashboardOverview(): Promise<DashboardOverview> {
  const w = await api.get<DashboardOverviewWire>("/api/core/dashboard/overview");
  return {
    generatedAt: w.generated_at,
    workflowCounts: w.workflow_counts,
    submissionsToday: w.submissions_today,
    quotesReceivedToday: w.quotes_received_today,
    remarketPending: w.remarket_pending,
    endorsementPending: w.endorsement_pending,
    bindersConfirmed: w.binders_confirmed,
    boundPremiumMtd: w.bound_premium_mtd,
    funnel: {
      stages: w.funnel.stages.map((s) => ({
        stage: s.stage,
        count: s.count,
        pctOfPriorStage: s.pct_of_prior_stage,
      })),
      gaps: w.funnel.gaps,
      overallConversionPct: w.funnel.overall_conversion_pct,
    },
    carrierPerformance: w.carrier_performance.map((c) => ({
      carrierName: c.carrier_name,
      submissionsApproached: c.submissions_approached,
      quoteRate: c.quote_rate,
      bindRate: c.bind_rate,
      overallHitRate: c.overall_hit_rate,
      lowVolumeFlag: c.low_volume_flag,
    })),
    timeToPlacement: w.time_to_placement.map((p) => ({
      carrierName: p.carrier_name,
      submissionsBound: p.submissions_bound,
      avgDays: p.avg_days,
      lowVolumeFlag: p.low_volume_flag,
    })),
    remarketValue: w.remarket_value.map((r) => ({
      account: r.account,
      triggerLevel: r.trigger_level,
      outcomeType: r.outcome_type,
      savingsAmount: r.savings_amount,
      note: r.note,
    })),
    recentActivity: w.recent_activity.map((a) => ({
      workflow: a.workflow,
      ref: a.ref,
      status: a.status,
      createdAt: a.created_at,
    })),
    remarketPipeline: w.remarket_pipeline.map((r) => ({
      namedInsured: r.named_insured,
      incumbentCarrierName: r.incumbent_carrier_name,
      triggerLevel: r.trigger_level,
      createdAt: r.created_at,
    })),
    diligentSearchAlerts: w.diligent_search_alerts.map((d) => ({
      submissionId: d.submission_id,
      onFile: d.on_file,
      note: d.note,
    })),
    dailyPipeline: w.daily_pipeline,
  };
}
