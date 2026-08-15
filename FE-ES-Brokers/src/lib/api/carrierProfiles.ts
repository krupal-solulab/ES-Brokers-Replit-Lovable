/**
 * Typed API calls for /api/es/carrier-profiles (G2 — Carrier Appetite Profile Store).
 *
 * Note: these types are defined here rather than from schema.d.ts because the
 * OpenAPI schema is regenerated separately.  Field names mirror the Pydantic
 * DTOs in carrier_profiles/router.py exactly.
 */
import { api } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PremiumBand {
  min: number;
  max: number;
}

export interface SubmissionRequirements {
  min_loss_run_years: number;
  required_documents: string[];
  acceptance_window_days: number | null;
}

export interface SeverityCeiling {
  max_single_claim_incurred: number;
}

export interface CarrierProfileVersion {
  version_id: string;
  carrier_id: string;
  carrier_name: string;
  class_codes_accepted: string[];
  class_codes_excluded: string[];
  states_licensed: string[];
  premium_band: PremiumBand;
  submission_requirements: SubmissionRequirements;
  severity_ceiling: SeverityCeiling;
  appetite_confidence: "high" | "medium" | "low";
  appetite_last_updated: string | null;
  historical_hit_rate_this_class: number;
  lines_written: string[];
  notes: string | null;
  form_metadata: Record<string, unknown>;
  gap_policy: Record<string, string>;
  supersedes_version_id: string | null;
  created_at: string;
  created_by: string;
  source: "SEED" | "HUMAN_EDIT" | "CI_METADATA_REFRESH";
}

export interface CarrierProfileWithHistory {
  current: CarrierProfileVersion | null;
  history: CarrierProfileVersion[];
}

export interface CarrierProfileUpdateIn {
  carrier_name: string;
  class_codes_accepted: string[];
  class_codes_excluded: string[];
  states_licensed: string[];
  premium_band: PremiumBand;
  submission_requirements: SubmissionRequirements;
  severity_ceiling: SeverityCeiling;
  appetite_confidence: "high" | "medium" | "low";
  appetite_last_updated: string | null;
  historical_hit_rate_this_class: number;
  lines_written: string[];
  notes: string | null;
  form_metadata: Record<string, unknown>;
  gap_policy: Record<string, string>;
}

export interface SuggestionActionOut {
  suggestion_id: string;
  carrier_id: string;
  action: "APPROVED" | "DISMISSED";
  profile_version_id: string | null;
}

// ── API calls ─────────────────────────────────────────────────────────────────

const BASE = "/api/es/carrier-profiles";

/** List current (latest) version of every carrier profile for this tenant. */
export function listCarrierProfiles() {
  return api.get<CarrierProfileVersion[]>(BASE);
}

/** Current version + full version history for one carrier. */
export function getCarrierProfile(carrierId: string) {
  return api.get<CarrierProfileWithHistory>(`${BASE}/${carrierId}`);
}

/** Create a new version from a human edit (SENIOR/ADMIN only). */
export function updateCarrierProfile(carrierId: string, data: CarrierProfileUpdateIn) {
  return api.post<CarrierProfileVersion>(`${BASE}/${carrierId}`, data);
}

/** Apply a pending CI suggestion as a new profile version (SENIOR/ADMIN only). */
export function approveSuggestion(carrierId: string, suggestionId: string) {
  return api.post<SuggestionActionOut>(
    `${BASE}/${carrierId}/suggestions/${suggestionId}/approve`,
  );
}

/** Dismiss a pending CI suggestion without applying it (SENIOR/ADMIN only). */
export function dismissSuggestion(carrierId: string, suggestionId: string) {
  return api.post<SuggestionActionOut>(
    `${BASE}/${carrierId}/suggestions/${suggestionId}/dismiss`,
  );
}

/** Seed profile store from JSON panel (ADMIN only, idempotent). */
export function seedCarrierProfiles() {
  return api.post<{ seeded: number; total_panel: number }>(`${BASE}/seed`);
}
