import { api } from "./client";

/** Product-wide data mode: "static" means EVERY screen is serving fixture /
 * deterministic sample data (mock mode, a disconnected connector, or an
 * out-of-quota AI provider) — never a half-live/half-static mix. */
export interface DataModeOut {
  mode: "live" | "static";
  reason: "" | "mock_mode" | "connector_disconnected" | "llm_insufficient_quota";
}

export function getDataMode() {
  return api.get<DataModeOut>("/api/core/app-config/data-mode");
}
