/**
 * Invite and reset links carry their one-time secret in the URL fragment (`/accept#token=...`) so it is never
 * sent to a server or written to access logs. This module reads it once and scrubs it from the address bar and
 * the history entry so it is not left in the URL, bookmarks or a shared screenshot.
 *
 * The value is kept in module memory (not storage) so a re-render, or React StrictMode running an initialiser
 * twice, still finds it after the URL has been cleaned.
 */
let captured: string | null = null;

export function parseFragmentToken(hash: string): string | null {
  const params = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
  const token = params.get("token");
  return token && token.trim() !== "" ? token.trim() : null;
}

/** Reads `#token=...` if present, removes the fragment from the URL, and returns the token (or null). */
export function captureFragmentToken(): string | null {
  const fromUrl = parseFragmentToken(window.location.hash);
  if (window.location.hash !== "") {
    // Keep history.state so the router's own bookkeeping survives; only the URL changes.
    window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
  }
  if (fromUrl) captured = fromUrl;
  return captured;
}

/** Forget the captured token once it has been spent (or the user leaves the page). */
export function clearCapturedToken(): void {
  captured = null;
}
