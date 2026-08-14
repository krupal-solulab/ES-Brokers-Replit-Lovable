/**
 * Typed calls for /api/es/agent-communication (Backend-AI-OS,
 * verticals/es/workflows/agent_communication/router.py). The third E&S
 * workflow — see docs/FE_CONTRACT_agent_communication.md in the backend repo.
 */
import { api } from "./client";
import type { components } from "./schema";

// Qualified with the module path — market_matching/package_assembly define
// their own `ReviewItemOut`/`RunRequest` classes too (see marketMatching.ts's
// comment on this).
// Extended with carrier_name/named_insured/trigger_type — list-view preview
// fields added to the backend's ReviewItemOut so threads sharing the same
// submission_id (one per matched carrier) are distinguishable in the list
// without opening each one; not yet in the generated schema.
export type ReviewItemOut =
  components["schemas"]["verticals__es__workflows__agent_communication__router__ReviewItemOut"] & {
    carrier_name?: string | null;
    named_insured?: string | null;
    trigger_type?: string | null;
  };
export type DraftCommunicationOut = components["schemas"]["DraftCommunicationOut"];
export type GroundingCitationOut = components["schemas"]["GroundingCitationOut"];
export type AgentCommActionVerb = "approve" | "edit" | "send" | "discard";

const BASE = "/api/es/agent-communication";

export function listAgentCommunication() {
  return api.get<ReviewItemOut[]>(BASE);
}

export function getAgentCommunication(itemId: string) {
  return api.get<ReviewItemOut>(`${BASE}/${itemId}`);
}

/** `trigger` is submitted as-is — POST /run has no fixture-ref shorthand
 * (unlike market_matching's submission_ref / package_assembly's
 * scenario_ref), so the FE_TRIGGERS below are the real Workflow_12 fixture
 * objects, embedded verbatim, not reconstructed. */
export function runAgentCommunication(trigger: Record<string, unknown>) {
  return api.post<ReviewItemOut>(`${BASE}/run`, { trigger });
}

export function actOnAgentCommunication(itemId: string, action: AgentCommActionVerb) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/${action}`);
}

/** Senior/admin only — clears the compliance-review gate on a No Market Found
 * draft (junior gets a real 403). */
export function complianceClear(itemId: string) {
  return api.post<ReviewItemOut>(`${BASE}/${itemId}/compliance-clear`);
}

export interface FixtureTrigger {
  ref: string;
  label: string;
  trigger: Record<string, unknown>;
}

/** The 6 Workflow_12 fixtures, embedded verbatim from
 * Data sets/Workflow 3/retail_comm_dataset/trigger_NN/trigger_input.json. */
export const FIXTURE_TRIGGERS: FixtureTrigger[] = [
  {
    ref: "trigger_01",
    label: "Delta Electric — Submission Acknowledgment",
    trigger: {
      trigger_type: "SUBMISSION_ACKNOWLEDGMENT",
      source_workflow: "Market Matching + Package Assembly",
      submission_id: "SUB-3301-multi",
      named_insured: "Delta Electric Services LLC",
      retail_agent_name: "Rachel Combs",
      retail_agency: "Harbor Retail Agency",
      agent_relationship_tenure: "2 years, moderate volume",
      carriers_approached: ["Ironclad Casualty Solutions", "Meridian Excess & Surplus"],
      carrier_statuses: {
        "Ironclad Casualty Solutions": "READY - submitted",
        "Meridian Excess & Surplus": "READY_WITH_GAP - submitted with disclosed gap",
      },
      expected_response_window_days: 10,
    },
  },
  {
    ref: "trigger_02",
    label: "Delta Electric (Palmetto blocked) — Missing Info Request",
    trigger: {
      trigger_type: "MISSING_INFO_REQUEST",
      source_workflow: "Package Assembly",
      submission_id: "SUB-3302",
      named_insured: "Delta Electric Services LLC",
      retail_agent_name: "Rachel Combs",
      retail_agency: "Harbor Retail Agency",
      agent_relationship_tenure: "2 years, moderate volume",
      carrier_name: "Palmetto Specialty Underwriters",
      package_status: "BLOCKED",
      blocking_items: [
        "Loss run only covers 3 of 5 years Palmetto requires",
        "Supplemental contractor questionnaire not provided",
      ],
    },
  },
  {
    ref: "trigger_03",
    label: "GreenLeaf Cultivation — No Market Found (compliance-gated)",
    trigger: {
      trigger_type: "NO_MARKET_FOUND",
      source_workflow: "Market Matching",
      submission_id: "SUB-3306",
      named_insured: "GreenLeaf Cultivation Facility LLC",
      retail_agent_name: "Angela Ruiz",
      retail_agency: "Summit Risk Partners",
      agent_relationship_tenure: "3 years, moderate volume",
      zero_match_result: true,
      class_code: "cannabis - cultivation",
      diligent_search: {
        required: true,
        documentation_status: "generated_from_carrier_panel_review",
      },
      carriers_reviewed_count: 6,
      COMPLIANCE_FLAG:
        "Confirm with compliance whether specific declining carrier names may be disclosed " +
        "to the retail agent/insured, or whether only an aggregate 'panel reviewed, no match' " +
        "statement is appropriate - do not assume carrier-level disclosure is safe by default.",
    },
  },
  {
    ref: "trigger_04",
    label: "Oakwood Apartment Homes — Placement Confirmation",
    trigger: {
      trigger_type: "PLACEMENT_CONFIRMATION",
      source_workflow: "Manual broker input (Quote Comparison workflow not yet built)",
      submission_id: "SUB-3303",
      named_insured: "Oakwood Apartment Homes LP",
      retail_agent_name: "James Foster",
      retail_agency: "Crestview Agency",
      agent_relationship_tenure: "5 years, high volume",
      carrier_name: "Coastal Mutual Specialty",
      bound_terms: {
        premium: "$81,500",
        limits: "Property $18,000,000 blanket; GL $1,000,000/$2,000,000",
        effective_date: "2027-08-15",
      },
    },
  },
  {
    ref: "trigger_05",
    label: "Delta Electric — No-Response Follow-up",
    trigger: {
      trigger_type: "NO_RESPONSE_FOLLOWUP",
      source_workflow: "Retail Agent Communication (self-triggered)",
      submission_id: "SUB-3302",
      named_insured: "Delta Electric Services LLC",
      retail_agent_name: "Rachel Combs",
      retail_agency: "Harbor Retail Agency",
      agent_relationship_tenure: "2 years, moderate volume",
      original_request_sent_date: "2027-07-14",
      days_since_original_request: 9,
      original_request_type: "MISSING_INFO_REQUEST",
      carrier_name: "Palmetto Specialty Underwriters",
      carrier_acceptance_window_days: 45,
      days_remaining_in_window: 36,
    },
  },
  {
    ref: "trigger_06",
    label: "Summit Roofing — Quote/Terms Summary",
    trigger: {
      trigger_type: "QUOTE_TERMS_SUMMARY",
      source_workflow: "Manual broker input (Quote Comparison workflow not yet built)",
      submission_id: "SUB-3304",
      named_insured: "Summit Roofing Group LLC",
      retail_agent_name: "Tom Whitfield",
      retail_agency: "Liberty Line Insurance",
      agent_relationship_tenure: "1 year, moderate volume, newer relationship",
      carrier_name: "Ironclad Casualty Solutions",
      quoted_terms: {
        premium: "$118,000",
        limits: "$1,000,000 / $2,000,000 aggregate",
        prior_expiring_premium_context:
          "Not applicable - new business, but incumbent-market rate benchmark suggests this " +
          "is roughly 60% above a clean contractor account of similar revenue",
      },
      quote_context:
        "Rate reflects Ironclad's pricing for elevated severity - 2 BI claims from falls, " +
        "one still open and reserved at $180,000",
    },
  },
];
