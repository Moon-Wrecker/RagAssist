/**
 * The access token lives in module memory only: never localStorage, sessionStorage or a cookie that script can
 * read. A page reload therefore starts signed out and recovers the session through the httpOnly refresh cookie.
 */
let accessToken: string | null = null;
const listeners = new Set<() => void>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  if (token === accessToken) return;
  accessToken = token;
  for (const listener of listeners) listener();
}

export function subscribeToken(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
