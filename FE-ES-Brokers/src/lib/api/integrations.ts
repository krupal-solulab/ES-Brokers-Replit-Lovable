/**
 * Typed calls for /api/core/integrations (Backend-AI-OS,
 * core/integrations/router.py) — the "Connect Gmail" flow. See
 * docs/CONNECTORS_NANGO.md in the backend repo: the frontend gets a Nango
 * Connect UI session token here, opens the hosted OAuth popup
 * (@nangohq/frontend), then reports the resulting connectionId back here.
 */
import { api } from "./client";

const BASE = "/api/core/integrations";

export interface ConnectSession {
  session_token: string;
  expires_at: string | null;
}

export function createConnectSession(provider: string) {
  return api.post<ConnectSession>(`${BASE}/connect-session`, { provider });
}

export interface Integration {
  provider: string;
  status: string;
}

export function listIntegrations() {
  return api.get<Integration[]>(`${BASE}/connections`);
}

export function confirmConnection(provider: string, nangoConnectionId: string) {
  return api.post<Integration>(`${BASE}/connections`, {
    provider,
    nango_connection_id: nangoConnectionId,
  });
}

export function disconnectIntegration(provider: string) {
  return api.post<Integration>(`${BASE}/connections/${provider}/disconnect`);
}

export const GOOGLE_MAIL_PROVIDER = "google-mail";
// Connect/disconnect only for now — no read/write wiring exists yet for any
// of these (see core/config.py's nango_integration_sheet/drive/calendar/slack/quickbooks).
export const GOOGLE_SHEET_PROVIDER = "google-sheet";
export const GOOGLE_DRIVE_PROVIDER = "google-drive";
export const GOOGLE_CALENDAR_PROVIDER = "google-calendar";
export const SLACK_PROVIDER = "slack";
export const QUICKBOOKS_PROVIDER = "quickbooks";
