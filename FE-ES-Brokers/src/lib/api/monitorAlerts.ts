/**
 * Typed calls for /api/core/monitors (G1 infra + G3 binder monitors).
 *
 * Alerts are tenant-scoped; the backend never leaks another tenant's data.
 * ``entity_ref`` semantics per workflow:
 *   binder_issuance / ISSUANCE_OVERDUE    → entity_ref === bind_id
 *   binder_issuance / OBLIGATION_REMINDER → entity_ref === "{bind_id}:{desc_hash}"
 */
import { api } from "./client";

export interface MonitorAlert {
  id: string;
  tenant_id: string;
  vertical: string;
  workflow: string;
  entity_ref: string;
  alert_type: string;
  severity: "INFO" | "WARN" | "URGENT";
  dedupe_key: string;
  payload: Record<string, unknown>;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

interface AlertListResponse {
  success: boolean;
  data: MonitorAlert[];
}

/** List MonitorAlerts for the current tenant.
 *  Optionally filter by workflow name and/or resolved state. */
export async function listMonitorAlerts(
  workflow?: string,
  resolved?: boolean,
): Promise<MonitorAlert[]> {
  const params = new URLSearchParams();
  if (workflow) params.set("workflow", workflow);
  if (resolved !== undefined) params.set("resolved", String(resolved));
  const qs = params.toString();
  const res = await api.get<AlertListResponse>(
    `/api/core/monitors/alerts${qs ? `?${qs}` : ""}`,
  );
  return res.data ?? [];
}

/** Dismiss (resolve) a MonitorAlert — SENIOR/ADMIN only. */
export async function dismissMonitorAlert(alertId: string): Promise<MonitorAlert> {
  const res = await api.post<{ success: boolean; data: MonitorAlert }>(
    `/api/core/monitors/alerts/${alertId}/dismiss`,
  );
  return res.data;
}

/** Dev-only: manually trigger one scheduled monitor for a given date.
 *  Returns the MonitorAlert rows produced (or already produced for that date).
 *  Endpoint returns 404 in production. SENIOR/ADMIN only. */
export async function runMonitor(
  name: string,
  asOf: string,
): Promise<MonitorAlert[]> {
  const res = await api.post<{ success: boolean; data: MonitorAlert[]; created: boolean }>(
    `/api/core/monitors/${encodeURIComponent(name)}/run?as_of=${encodeURIComponent(asOf)}`,
  );
  return res.data ?? [];
}
