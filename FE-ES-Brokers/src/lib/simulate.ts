/**
 * Fake network call for UI-only flows (auth dialogs, /demo form) that don't
 * have a real backend wired up yet. Resolves `result` after a realistic
 * delay, with a small deliberate failure rate so the error state in the
 * calling form is actually reachable while demoing/testing — not dead code.
 *
 * TODO: every call site using this should be swapped for a real API call
 * (Supabase/Clerk auth, or a POST to a server route backed by Resend/
 * Web3Forms for the demo form) once a backend is wired up. Nothing here
 * persists anything.
 */
export function simulateRequest<T>(
  result: T,
  { delayMs = 900, failureRate = 0.12 }: { delayMs?: number; failureRate?: number } = {},
): Promise<T> {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (Math.random() < failureRate) {
        reject(new Error("Something went wrong on our end. Please try again."));
        return;
      }
      resolve(result);
    }, delayMs);
  });
}
