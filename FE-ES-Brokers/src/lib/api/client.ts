/**
 * Single fetch wrapper for calls to Backend-AI-OS. Every real API call goes
 * through this — nothing else in the app calls fetch() against the backend
 * directly.
 *
 * Attaches the Phase-0 header-stub auth (x-tenant-id / x-user-id / x-role —
 * see Backend-AI-OS/src/core/tenancy/dependencies.py) and normalizes
 * FastAPI's `{"detail": ...}` error responses into a plain Error, so
 * existing `catch (err) { err instanceof Error ? err.message : ... }` call
 * sites (see AuthDialog.tsx / DemoPage.tsx) work unchanged.
 *
 * Headers come from whoever is logged in this tab/window (see identity.ts,
 * sessionStorage-backed) — read fresh on every call, not computed once at
 * module load, so switching identity takes effect immediately without a
 * reload. Falls back to the old build-time Vite env vars only if no one has
 * logged in yet in this tab (e.g. mid-transition, or a route that isn't
 * behind the login guard), so a request never goes out with zero identity
 * headers.
 */
import { getIdentity } from "./identity";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined;
const DEMO_TENANT_ID = import.meta.env.VITE_DEMO_TENANT_ID as string | undefined;
const DEMO_USER_ID = import.meta.env.VITE_DEMO_USER_ID as string | undefined;
const DEMO_ROLE = import.meta.env.VITE_DEMO_ROLE as string | undefined;

function authHeaders(): Record<string, string> {
  const identity = getIdentity();
  const headers: Record<string, string> = {};
  const tenantId = identity?.tenantId ?? DEMO_TENANT_ID;
  const userId = identity?.userId ?? DEMO_USER_ID;
  const role = identity?.role ?? DEMO_ROLE;
  if (tenantId) headers["x-tenant-id"] = tenantId;
  if (userId) headers["x-user-id"] = userId;
  if (role) headers["x-role"] = role;
  return headers;
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
    ) {
      return (body as { detail: string }).detail;
    }
  } catch {
    // response wasn't JSON — fall through to the status-based message
  }
  return `Request failed (${res.status} ${res.statusText})`;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("VITE_API_BASE_URL is not set — see .env.example");
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      // Free ngrok tunnels serve an HTML "are you a human?" interstitial
      // (no CORS headers at all) to plain browser-looking requests unless
      // this is set — without it, some calls silently come back as a
      // browser-reported CORS error even though the real backend never
      // saw the request. Harmless/no-op against a non-ngrok backend.
      "ngrok-skip-browser-warning": "true",
      ...authHeaders(),
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (!res.ok) {
    throw new Error(await parseErrorDetail(res));
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: "POST",
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    }),
};
