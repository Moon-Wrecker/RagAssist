import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, NetworkError } from "./errors";
import { apiFetch, apiJson, onSessionLost, refreshSession } from "./http";
import { getAccessToken, setAccessToken } from "./token-store";
import { callsTo, fakeSession, fakeToken, jsonResponse, mockFetch } from "@/test/helpers";

const REFRESH = "POST /v1/auth/refresh";

beforeEach(() => setAccessToken(null));
afterEach(() => setAccessToken(null));

describe("apiFetch", () => {
  it("sends the in-memory bearer token", async () => {
    const token = fakeToken("access");
    setAccessToken(token);
    const fetchMock = mockFetch({ "GET /v1/things": ({ headers }) => jsonResponse({ auth: headers.get("Authorization") }) });
    const response = await apiFetch("/v1/things");
    expect(await response.json()).toEqual({ auth: `Bearer ${token}` });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends no Authorization header when signed out", async () => {
    mockFetch({ "GET /v1/things": ({ headers }) => jsonResponse({ has: headers.has("Authorization") }) });
    expect(await (await apiFetch("/v1/things")).json()).toEqual({ has: false });
  });

  it("refreshes once on 401 and retries the request with the new token", async () => {
    const stale = fakeToken("stale");
    const fresh = fakeToken("fresh");
    setAccessToken(stale);
    const fetchMock = mockFetch({
      "GET /v1/things": [
        ({ headers }) =>
          headers.get("Authorization") === `Bearer ${stale}` ? jsonResponse({ detail: "expired" }, 401) : jsonResponse({ ok: true }),
      ],
      [REFRESH]: () => jsonResponse(fakeSession(fresh)),
    });
    const response = await apiFetch("/v1/things");
    expect(response.status).toBe(200);
    expect(getAccessToken()).toBe(fresh);
    expect(callsTo(fetchMock, REFRESH)).toHaveLength(1);
    const retry = callsTo(fetchMock, "GET /v1/things")[1]!;
    expect(new Headers((retry[1] as RequestInit).headers).get("Authorization")).toBe(`Bearer ${fresh}`);
  });

  it("shares one refresh between concurrent 401s (single flight)", async () => {
    const stale = fakeToken("stale");
    const fresh = fakeToken("fresh");
    setAccessToken(stale);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    const fetchMock = mockFetch({
      "GET /v1/a": ({ headers }) => (headers.get("Authorization") === `Bearer ${fresh}` ? jsonResponse({ a: 1 }) : jsonResponse({}, 401)),
      "GET /v1/b": ({ headers }) => (headers.get("Authorization") === `Bearer ${fresh}` ? jsonResponse({ b: 1 }) : jsonResponse({}, 401)),
      "GET /v1/c": ({ headers }) => (headers.get("Authorization") === `Bearer ${fresh}` ? jsonResponse({ c: 1 }) : jsonResponse({}, 401)),
      [REFRESH]: async () => {
        await gate;
        return jsonResponse(fakeSession(fresh));
      },
    });
    const all = Promise.all([apiFetch("/v1/a"), apiFetch("/v1/b"), apiFetch("/v1/c")]);
    await vi.waitFor(() => expect(callsTo(fetchMock, REFRESH)).toHaveLength(1));
    release();
    const responses = await all;
    expect(responses.map((r) => r.status)).toEqual([200, 200, 200]);
    expect(callsTo(fetchMock, REFRESH)).toHaveLength(1);
  });

  it("does not refresh again when another request already replaced the token", async () => {
    const stale = fakeToken("stale");
    const fresh = fakeToken("fresh");
    setAccessToken(stale);
    const fetchMock = mockFetch({
      "GET /v1/things": [
        () => {
          setAccessToken(fresh); // a concurrent refresh finished while this request was in flight
          return jsonResponse({}, 401);
        },
        () => jsonResponse({ ok: true }),
      ],
    });
    const response = await apiFetch("/v1/things");
    expect(response.status).toBe(200);
    expect(callsTo(fetchMock, REFRESH)).toHaveLength(0);
  });

  it("ends the session when the refresh is refused", async () => {
    setAccessToken(fakeToken("stale"));
    const lost = vi.fn();
    const off = onSessionLost(lost);
    mockFetch({
      "GET /v1/things": () => jsonResponse({ detail: "expired" }, 401),
      [REFRESH]: () => jsonResponse({ detail: "no session" }, 401),
    });
    const response = await apiFetch("/v1/things");
    off();
    expect(response.status).toBe(401);
    expect(getAccessToken()).toBeNull();
    expect(lost).toHaveBeenCalledTimes(1);
  });

  it("keeps the session when the refresh cannot reach the server", async () => {
    const stale = fakeToken("stale");
    setAccessToken(stale);
    const lost = vi.fn();
    const off = onSessionLost(lost);
    mockFetch({
      "GET /v1/things": () => jsonResponse({}, 401),
      [REFRESH]: () => {
        throw new TypeError("network down");
      },
    });
    await expect(apiFetch("/v1/things")).rejects.toBeInstanceOf(NetworkError);
    off();
    expect(lost).not.toHaveBeenCalled();
    expect(getAccessToken()).toBe(stale);
  });

  it("does not refresh for requests that opt out (sign-in)", async () => {
    const fetchMock = mockFetch({ "POST /v1/auth/login": () => jsonResponse({ detail: "no" }, 401) });
    const response = await apiFetch("/v1/auth/login", { method: "POST", retryOnUnauthorized: false });
    expect(response.status).toBe(401);
    expect(callsTo(fetchMock, REFRESH)).toHaveLength(0);
  });

  it("starts a new refresh after the previous one settled", async () => {
    const fetchMock = mockFetch({ [REFRESH]: () => jsonResponse(fakeSession(fakeToken("t"))) });
    await refreshSession();
    await refreshSession();
    expect(callsTo(fetchMock, REFRESH)).toHaveLength(2);
  });

  it("sends the refresh as a same-origin POST so the cookie travels", async () => {
    const fetchMock = mockFetch({ [REFRESH]: () => jsonResponse(fakeSession(fakeToken("t"))) });
    await refreshSession();
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(init.credentials).toBe("same-origin");
    expect(init.method).toBe("POST");
  });
});

describe("apiJson", () => {
  it("throws an ApiError carrying the server's detail and Retry-After", async () => {
    mockFetch({ "GET /v1/things": () => jsonResponse({ detail: "Too many attempts." }, 429, { "Retry-After": "120" }) });
    const error = await apiJson("/v1/things").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 429, detail: "Too many attempts.", retryAfter: 120 });
  });

  it("reads FastAPI validation arrays", async () => {
    mockFetch({ "GET /v1/things": () => jsonResponse({ detail: [{ msg: "Field required" }, { msg: "Too short" }] }, 422) });
    const error = await apiJson("/v1/things").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 422, detail: "Field required Too short" });
  });

  it("returns undefined for 204", async () => {
    mockFetch({ "DELETE /v1/things": () => new Response(null, { status: 204 }) });
    expect(await apiJson("/v1/things", { method: "DELETE" })).toBeUndefined();
  });
});
