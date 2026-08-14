/**
 * The logged-in identity, persisted to sessionStorage — isolated per
 * browser tab/window (unlike localStorage, which is shared across every
 * tab of the same origin), which is exactly what lets two separate windows
 * be logged in as two different people at once.
 *
 * Kept in its own module (not auth.ts or client.ts) so both can import it
 * without a circular dependency: client.ts's authHeaders() reads it,
 * auth.ts's login() writes it.
 */

const STORAGE_KEY = "coverline-identity";

export interface Identity {
  tenantId: string;
  userId: string;
  email: string;
  name: string | null;
  role: string;
  vertical: string;
}

export function getIdentity(): Identity | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Identity) : null;
  } catch {
    return null; // sessionStorage unavailable (private browsing, etc.) — treat as logged out
  }
}

export function setIdentity(identity: Identity): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(identity));
  } catch {
    // sessionStorage unavailable — identity just won't persist across reloads this tab.
  }
}

export function clearIdentity(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // sessionStorage unavailable — nothing to clear.
  }
}
