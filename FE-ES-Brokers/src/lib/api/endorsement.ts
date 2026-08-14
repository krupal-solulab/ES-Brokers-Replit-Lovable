/**
 * Typed calls for /api/es/endorsement (Backend-AI-OS,
 * verticals/es/workflows/endorsement/router.py). The sixth E&S workflow —
 * see docs/FE_CONTRACT_endorsement.md in the backend repo.
 */
import { api } from "./client";
import type { components } from "./schema";

// Qualified with the module path — every ES workflow router defines its own
// `ReviewItemOut`/`RunRequest` classes (see marketMatching.ts's comment).
// `DiscrepancyOut` needs the same treatment — binder_issuance defines its
// own class with the same name.
export type ReviewItemOut =
  components["schemas"]["verticals__es__workflows__endorsement__router__ReviewItemOut"];
export type EndorsementRequestPayload = components["schemas"]["EndorsementRequestPayload"];
export type DiscrepancyOut =
  components["schemas"]["verticals__es__workflows__endorsement__schema__DiscrepancyOut"];
export type DiscrepancyResolution = "accept_carrier_issuance" | "flag_carrier_error";

const BASE = "/api/es/endorsement";

export function listEndorsement() {
  return api.get<ReviewItemOut[]>(BASE);
}

export function getEndorsement(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

export function runEndorsement(scenarioRef: string) {
  return api.post<ReviewItemOut>(`${BASE}/run`, { scenario_ref: scenarioRef });
}

/** Required before the ENDORSEMENT_CONFIRMED downstream trigger can fire. */
export function resolveDiscrepancy(itemId: string, resolution: DiscrepancyResolution) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/resolve-discrepancy`, { resolution });
}

/** Senior/admin only — project-wide SEND rule. */
export function sendEndorsement(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/send`);
}

export function escalateEndorsement(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/escalate`);
}

/** Additive alongside the fixture-scenario run above: starts a real
 * pre-issuance pass from an actual, already-SENT Binder & Issuance bind's
 * real terms. The change type/detail are broker-supplied — never inferred
 * from raw email text (the retail agent's request email is free-flowing
 * natural language with no reliable type signal a regex could extract
 * without real risk of misclassifying a material change as routine). */
export function runEndorsementFromBinder(
  binderIssuanceItemId: string,
  changeType: string,
  changeDetail: string,
) {
  return api.post<ReviewItemOut>(`${BASE}/run-live-from-binder`, {
    binder_issuance_item_id: binderIssuanceItemId,
    change_type: changeType,
    change_detail: changeDetail,
  });
}

export interface LiveInboxMessage {
  id: string;
  subject: string;
}

/** Real Gmail messages that could be this request's issued endorsement —
 * matched server-side by the request's own real named insured. Requires
 * Gmail connected + backend CONNECTORS_MODE=live. */
export function listLiveInbox(itemId: string) {
  return api.get<LiveInboxMessage[]>(`${BASE}/live-inbox?item_id=${encodeURIComponent(itemId)}`);
}

/** Attaches a real carrier-issued-endorsement email — runs EP-05's
 * item-level reconciliation for real. */
export function attachLiveIssuedEndorsement(itemId: string, messageId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/attach-live-issued-endorsement`, {
    message_id: messageId,
  });
}

export interface ChangeType {
  value: string;
  label: string;
}

/** Mirrors classification_engine.py's 7-value taxonomy — for the "Start
 * endorsement request" type picker. Order roughly matches how commonly
 * each type appears in real request patterns. */
export const CHANGE_TYPES: ChangeType[] = [
  { value: "additional_insured_endorsement", label: "Additional insured" },
  { value: "limit_increase", label: "Limit increase" },
  { value: "add_operations_class", label: "New operations class" },
  { value: "add_location", label: "New location" },
  { value: "employee_count_update", label: "Headcount / exposure update" },
  { value: "address_correction", label: "Address correction" },
  { value: "other", label: "Other" },
];

export interface FixtureScenario {
  ref: string;
  label: string;
}

/** The 6 Workflow_15 fixture scenarios (see
 * Data sets/Workflow 6/endorsement_dataset/README.md). */
export const FIXTURE_SCENARIOS: FixtureScenario[] = [
  { ref: "scenario_01", label: "Continental Freight — add additional insured (routine)" },
  { ref: "scenario_02", label: "Summit Roofing — limit increase (UW review required)" },
  { ref: "scenario_03", label: "Delta Electric — new operations class (appetite unknown)" },
  { ref: "scenario_04", label: "Oakwood Apartment Homes — add location (material, in appetite)" },
  { ref: "scenario_05", label: "Continental Freight — issued endorsement missing an item" },
  { ref: "scenario_06", label: "Clearpath Bookkeeping — headcount update (routine control case)" },
];
