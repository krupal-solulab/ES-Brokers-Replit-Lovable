---
name: Product-wide static data fallback
description: How live-vs-static data mode is resolved and enforced across connectors, LLM, and the FE banner.
---

Rule: one shared resolver (`core/data_mode.py`) decides live vs static (reasons: mock_mode / connector_disconnected / llm_insufficient_quota). An HTTP middleware in `main.py` resolves it once per request and pins it in a contextvar; both `build_connector_service` and `build_llm_service` consult that contextvar so a request is never half-live/half-static.

**Why:** demo/sales environments must keep serving fixture data (never a 428 or LLM crash) when Gmail is disconnected or OpenAI is out of quota, while a Live+connected+funded setup stays byte-identical to before.

**How to apply:**
- Static output only ever comes from the existing MockConnectorService/fixtures path — never a parallel data source, never fabricated numbers.
- Writeback/outbound connector methods (send_email, put_file, upload_file, append_rows, create_event, send_slack_message) are deliberately EXCLUDED from the fallback — they still raise ConnectorNotConnectedError so routers report "skipped — not connected" instead of pretending a real write happened.
- Live-ingestion helpers that truly need the live service must use `unwrap_live_connector()` (the factory returns a StaticFallbackConnectorService wrapper in live mode, so bare `isinstance(..., LiveNangoConnectorService)` checks break).
- LLM quota flag: only insufficient_quota/billing errors flip it (plain 429 rate limits do not); process-local with 5-min TTL — a known single-process limitation.
- Connector check covers ALL four registered connectors (mail, sheet, drive, slack) as one combined per-tenant cached answer (15s TTL); ANY missing one flips the whole product static. Connect/disconnect endpoints must call `invalidate_connection_cache(tenant_id)`.
- Billing signals that flip the quota flag: insufficient_quota, "exceeded your current quota", billing_hard_limit_reached, HTTP 402. No proactive balance polling — OpenAI exposes no billing/credit API to standard keys, so detection stays reactive.
- FE banner lives in AppShell (`StaticDataBanner`, polls GET /api/core/app-config/data-mode every 30s).
