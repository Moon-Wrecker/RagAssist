import { apiErrorFromResponse } from "./errors";
import { apiFetch, apiJson, jsonBody, refreshSession } from "./http";
import { setAccessToken } from "./token-store";
import type { AcceptRequest, LoginRequest, Me, Session } from "./types";

export async function login(request: LoginRequest): Promise<Session> {
  const session = await apiJson<Session>("/v1/auth/login", {
    method: "POST",
    retryOnUnauthorized: false,
    ...jsonBody(request),
  });
  setAccessToken(session.access_token);
  return session;
}

/** Spends an invite or password-reset link: sets the password and signs in. */
export async function acceptLink(request: AcceptRequest): Promise<Session> {
  const session = await apiJson<Session>("/v1/auth/invites/accept", {
    method: "POST",
    retryOnUnauthorized: false,
    ...jsonBody(request),
  });
  setAccessToken(session.access_token);
  return session;
}

/** Restore a session after a reload from the httpOnly cookie. Null when there is none. */
export function restoreSession(): Promise<Session | null> {
  return refreshSession();
}

export function fetchMe(): Promise<Me> {
  return apiJson<Me>("/v1/auth/me");
}

/** Ends the server-side session and forgets the token. The local token is cleared even if the call fails. */
export async function logout(): Promise<void> {
  try {
    const response = await apiFetch("/v1/auth/logout", { method: "POST", retryOnUnauthorized: false });
    if (!response.ok && response.status !== 401) throw await apiErrorFromResponse(response);
  } finally {
    setAccessToken(null);
  }
}
