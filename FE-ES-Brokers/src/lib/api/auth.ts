/**
 * Email-based-role login (Backend-AI-OS, core/auth/router.py). Still
 * Phase-0 stub auth — no password, just an email -> real User lookup that
 * determines which x-tenant-id/x-user-id/x-role headers `client.ts` should
 * start sending. See identity.ts for how the result is persisted.
 */
import { apiFetch } from "./client";
import { setIdentity, type Identity } from "./identity";

interface LoginResponse {
  tenant_id: string;
  user_id: string;
  email: string;
  name: string | null;
  role: string;
  vertical: string;
}

export async function login(email: string): Promise<Identity> {
  const res = await apiFetch<LoginResponse>("/api/core/auth/login", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  const identity: Identity = {
    tenantId: res.tenant_id,
    userId: res.user_id,
    email: res.email,
    name: res.name,
    role: res.role,
    vertical: res.vertical,
  };
  setIdentity(identity);
  return identity;
}

export { getIdentity, clearIdentity, type Identity } from "./identity";
