import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { acceptLink, login, logout, restoreSession } from "./auth";
import { ApiError } from "./errors";
import { getAccessToken, setAccessToken } from "./token-store";
import { callsTo, fakeSession, fakeToken, jsonResponse, mockFetch } from "@/test/helpers";

beforeEach(() => setAccessToken(null));
afterEach(() => setAccessToken(null));

describe("auth api", () => {
  it("login keeps the access token in memory only", async () => {
    const token = fakeToken("access");
    mockFetch({ "POST /v1/auth/login": () => jsonResponse(fakeSession(token)) });
    const session = await login({ workspace: "example", email: "person@example.test", password: fakeToken("pw") });
    expect(session.user.role).toBe("user");
    expect(getAccessToken()).toBe(token);
    expect(JSON.stringify({ ...localStorage })).not.toContain(token);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(token);
    expect(document.cookie).not.toContain(token);
  });

  it("login surfaces a 401 without trying to refresh", async () => {
    const fetchMock = mockFetch({ "POST /v1/auth/login": () => jsonResponse({ detail: "Invalid." }, 401) });
    await expect(login({ workspace: "w", email: "e@example.test", password: "x" })).rejects.toMatchObject({ status: 401 });
    expect(callsTo(fetchMock, "POST /v1/auth/refresh")).toHaveLength(0);
    expect(getAccessToken()).toBeNull();
  });

  it("acceptLink signs in with the returned session", async () => {
    const token = fakeToken("access");
    const fetchMock = mockFetch({ "POST /v1/auth/invites/accept": () => jsonResponse(fakeSession(token, "admin")) });
    const session = await acceptLink({ token: fakeToken("link"), password: fakeToken("pw") });
    expect(session.user.role).toBe("admin");
    expect(getAccessToken()).toBe(token);
    const body = JSON.parse(String((fetchMock.mock.calls[0]![1] as RequestInit).body)) as Record<string, string>;
    expect(Object.keys(body).sort()).toEqual(["password", "token"]);
  });

  it("restoreSession returns null when there is no refresh cookie", async () => {
    mockFetch({ "POST /v1/auth/refresh": () => jsonResponse({ detail: "none" }, 401) });
    expect(await restoreSession()).toBeNull();
  });

  it("logout clears the token even when the server call fails", async () => {
    setAccessToken(fakeToken("access"));
    mockFetch({ "POST /v1/auth/logout": () => jsonResponse({ detail: "boom" }, 500) });
    await expect(logout()).rejects.toBeInstanceOf(ApiError);
    expect(getAccessToken()).toBeNull();
  });

  it("logout succeeds on 204", async () => {
    setAccessToken(fakeToken("access"));
    mockFetch({ "POST /v1/auth/logout": () => new Response(null, { status: 204 }) });
    await logout();
    expect(getAccessToken()).toBeNull();
  });
});
