import { apiErrorFromResponse, NetworkError } from "./errors";
import { getAccessToken, setAccessToken } from "./token-store";
import type { Session } from "./types";

/**
 * Same-origin API client.
 *
 * - Every request carries the in-memory bearer token.
 * - A 401 triggers one refresh through the httpOnly refresh cookie and one retry of the original request.
 * - Refreshes are single-flight: any number of concurrent 401s share one `POST /v1/auth/refresh`, because the
 *   server rotates the cookie and treats a replayed token as theft (ADR 0007). A Web Lock additionally
 *   serialises refreshes across tabs where the browser has the API.
 * - If the refresh itself is refused the session is over: the token is cleared and `onSessionLost` listeners run.
 */

const REFRESH_PATH = "/v1/auth/refresh";
const REFRESH_LOCK = "ragassist-refresh";

const sessionLostListeners = new Set<() => void>();

export function onSessionLost(listener: () => void): () => void {
  sessionLostListeners.add(listener);
  return () => {
    sessionLostListeners.delete(listener);
  };
}

/** Tell the app the session is over (refresh refused). Used by callers that manage their own requests. */
export function notifySessionLost(): void {
  for (const listener of sessionLostListeners) listener();
}

async function send(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(path, { credentials: "same-origin", ...init });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new NetworkError({ cause: error });
  }
}

let inFlightRefresh: Promise<Session | null> | null = null;

async function runRefresh(): Promise<Session | null> {
  const response = await send(REFRESH_PATH, { method: "POST", headers: { Accept: "application/json" } });
  if (response.status === 401 || response.status === 403) {
    setAccessToken(null);
    return null;
  }
  if (!response.ok) throw await apiErrorFromResponse(response);
  const session = (await response.json()) as Session;
  setAccessToken(session.access_token);
  return session;
}

/**
 * Exchange the refresh cookie for a new access token. Resolves to null when there is no valid session.
 * Rejects (NetworkError / ApiError) when the server could not give an answer, which does not end the session.
 */
export function refreshSession(): Promise<Session | null> {
  if (inFlightRefresh) return inFlightRefresh;
  const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
  const attempt = locks ? locks.request(REFRESH_LOCK, runRefresh) : runRefresh();
  const shared = attempt.finally(() => {
    if (inFlightRefresh === shared) inFlightRefresh = null;
  });
  inFlightRefresh = shared;
  return shared;
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | null;
  /** Set false for requests that must not attempt a refresh on 401 (sign-in, accept). */
  retryOnUnauthorized?: boolean;
}

function withAuth(init: RequestInit): RequestInit {
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers };
}

/** `fetch` with auth, refresh-on-401 and typed network failures. Returns the raw Response (so streams work). */
export async function apiFetch(path: string, options: ApiFetchOptions = {}): Promise<Response> {
  const { retryOnUnauthorized = true, ...init } = options;
  const sentToken = getAccessToken();
  const first = await send(path, withAuth(init));
  if (first.status !== 401 || !retryOnUnauthorized) return first;

  // Another request may have refreshed while this one was in flight: retry with the new token, no second refresh.
  const current = getAccessToken();
  if (current === null || current === sentToken) {
    const session = await refreshSession();
    if (!session) {
      notifySessionLost();
      return first;
    }
  }
  return send(path, withAuth(init));
}

export async function apiJson<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  const response = await apiFetch(path, { ...options, headers });
  if (!response.ok) throw await apiErrorFromResponse(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function jsonBody(value: unknown): Pick<RequestInit, "body" | "headers"> {
  return { body: JSON.stringify(value), headers: { "Content-Type": "application/json" } };
}
