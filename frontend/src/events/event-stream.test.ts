import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { onSessionLost } from "@/api/http";
import { getAccessToken, setAccessToken } from "@/api/token-store";
import { callsTo, fakeSession, fakeToken, frame, jsonResponse, mockFetch, sseResponse } from "@/test/helpers";
import { backoffDelay, runEventStream } from "./event-stream";
import type { LiveEvent } from "./invalidation";

const EVENTS = "GET /v1/events";
const REFRESH = "POST /v1/auth/refresh";

beforeEach(() => setAccessToken(fakeToken("access")));
afterEach(() => setAccessToken(null));

function harness(overrides: Partial<Parameters<typeof runEventStream>[0]> = {}) {
  const controller = new AbortController();
  const events: LiveEvent[] = [];
  const delays: number[] = [];
  const onReconnected = vi.fn();
  const statuses: string[] = [];
  // Start on a microtask so the test can install its fetch mock right after calling harness().
  const done = Promise.resolve().then(() => runEventStream({
    signal: controller.signal,
    onEvent: (event) => events.push(event),
    onReconnected,
    onStatus: (s) => statuses.push(s),
    random: () => 0,
    // Records the delay and yields a real macrotask, so timers (the test's abort) still get to run.
    sleep: (ms) =>
      new Promise<void>((resolve) => {
        delays.push(ms);
        setTimeout(resolve, 1);
      }),
    ...overrides,
  }));
  return { controller, events, delays, onReconnected, statuses, done };
}

describe("backoffDelay", () => {
  it("doubles up to the cap, with jitter between half and full", () => {
    expect(backoffDelay(0, 1000, 30000, () => 0)).toBe(500);
    expect(backoffDelay(0, 1000, 30000, () => 1)).toBe(1000);
    expect(backoffDelay(3, 1000, 30000, () => 1)).toBe(8000);
    expect(backoffDelay(20, 1000, 30000, () => 1)).toBe(30000);
  });
});

describe("runEventStream", () => {
  it("sends the bearer token with an SSE Accept header and delivers parsed events", async () => {
    const token = getAccessToken();
    const { controller, events, done } = harness();
    const fetchMock = mockFetch({
      [EVENTS]: ({ headers }) => {
        expect(headers.get("Authorization")).toBe(`Bearer ${token}`);
        expect(headers.get("Accept")).toBe("text/event-stream");
        setTimeout(() => controller.abort(), 30);
        return sseResponse([
          frame("ready"),
          ": ping\n\n",
          frame("message.created", { conversation_id: "c1" }),
          frame("job.updated", { job_id: "j1", document_id: "d1" }),
        ], { hold: true });
      },
    });
    await done;
    expect(events.map((e) => e.type)).toEqual(["ready", "message.created", "job.updated"]);
    expect(events[1]?.data).toEqual({ conversation_id: "c1" });
    expect(fetchMock).toHaveBeenCalled();
  });

  it("tolerates a frame split across chunks and malformed data", async () => {
    const { controller, events, done } = harness();
    mockFetch({
      [EVENTS]: () => {
        setTimeout(() => controller.abort(), 30);
        return sseResponse(["event: message.cre", 'ated\ndata: {"conversation_id":"c9"}\n\n', "event: odd\ndata: not json\n\n"], { hold: true });
      },
    });
    await done;
    expect(events).toEqual([
      { type: "message.created", data: { conversation_id: "c9" } },
      { type: "odd", data: {} },
    ]);
  });

  it("reconnects with exponential backoff after failures and resets after ready", async () => {
    const { controller, delays, statuses, done } = harness();
    let call = 0;
    mockFetch({
      [EVENTS]: () => {
        call += 1;
        if (call <= 3) throw new TypeError("offline");
        if (call === 4) return sseResponse([frame("ready")]); // connects, then the stream ends
        setTimeout(() => controller.abort(), 10);
        return sseResponse([], { hold: true });
      },
    });
    await done;
    // base 1000 with random() = 0 gives half the ceiling: 500, 1000, 2000; then ready resets the attempt.
    expect(delays.slice(0, 4)).toEqual([500, 1000, 2000, 500]);
    expect(statuses[0]).toBe("connecting");
    expect(statuses).toContain("connected");
    expect(statuses).toContain("reconnecting");
  });

  it("asks the caller to refetch everything after a reconnect, but not after the first connection", async () => {
    const { controller, onReconnected, done } = harness();
    let call = 0;
    mockFetch({
      [EVENTS]: () => {
        call += 1;
        if (call === 1) return sseResponse([frame("ready")]);
        setTimeout(() => controller.abort(), 10);
        return sseResponse([frame("ready")], { hold: true });
      },
    });
    await done;
    expect(onReconnected).toHaveBeenCalledTimes(1);
  });

  it("refreshes the token on reauth and reconnects at once without backing off", async () => {
    const fresh = fakeToken("fresh");
    const { controller, delays, done } = harness();
    let call = 0;
    const fetchMock = mockFetch({
      [EVENTS]: ({ headers }) => {
        call += 1;
        if (call === 1) return sseResponse([frame("ready"), frame("reauth")]);
        expect(headers.get("Authorization")).toBe(`Bearer ${fresh}`);
        setTimeout(() => controller.abort(), 10);
        return sseResponse([frame("ready")], { hold: true });
      },
      [REFRESH]: () => jsonResponse(fakeSession(fresh)),
    });
    await done;
    expect(callsTo(fetchMock, REFRESH)).toHaveLength(1);
    expect(delays).toEqual([]);
  });

  it("stops and ends the session when reauth cannot be refreshed", async () => {
    const lost = vi.fn();
    const off = onSessionLost(lost);
    const { done } = harness();
    const fetchMock = mockFetch({
      [EVENTS]: () => sseResponse([frame("ready"), frame("reauth")]),
      [REFRESH]: () => jsonResponse({ detail: "gone" }, 401),
    });
    await done;
    off();
    expect(lost).toHaveBeenCalledTimes(1);
    expect(callsTo(fetchMock, EVENTS)).toHaveLength(1);
  });

  it("refreshes and retries when the connection itself answers 401", async () => {
    const fresh = fakeToken("fresh");
    const { controller, done } = harness();
    let call = 0;
    const fetchMock = mockFetch({
      [EVENTS]: () => {
        call += 1;
        if (call === 1) return jsonResponse({ detail: "expired" }, 401);
        setTimeout(() => controller.abort(), 10);
        return sseResponse([frame("ready")], { hold: true });
      },
      [REFRESH]: () => jsonResponse(fakeSession(fresh)),
    });
    await done;
    expect(callsTo(fetchMock, REFRESH)).toHaveLength(1);
  });

  it("gives up quietly when the session is gone (401 and refresh refused)", async () => {
    const lost = vi.fn();
    const off = onSessionLost(lost);
    const { done } = harness();
    mockFetch({
      [EVENTS]: () => jsonResponse({ detail: "expired" }, 401),
      [REFRESH]: () => jsonResponse({ detail: "gone" }, 401),
    });
    await done;
    off();
    expect(lost).toHaveBeenCalledTimes(1);
  });

  it("backs off on a 429 from the connection cap instead of hammering", async () => {
    const { controller, delays, done } = harness();
    let call = 0;
    mockFetch({
      [EVENTS]: () => {
        call += 1;
        if (call === 1) return jsonResponse({ detail: "Too many streams" }, 429, { "Retry-After": "7" });
        setTimeout(() => controller.abort(), 10);
        return sseResponse([], { hold: true });
      },
    });
    await done;
    expect(delays[0]).toBe(7000); // Retry-After wins over the 500 ms backoff
  });

  it("treats a silent connection as dead and reconnects", async () => {
    vi.useFakeTimers();
    try {
      const { controller, delays, done } = harness({ idleTimeoutMs: 1000 });
      let call = 0;
      mockFetch({
        [EVENTS]: () => {
          call += 1;
          if (call === 2) {
            setTimeout(() => controller.abort(), 10);
            return sseResponse([], { hold: true });
          }
          // First connection: says ready, then goes silent (no events, no pings).
          return sseResponse([frame("ready")], { hold: true });
        },
      });
      await vi.advanceTimersByTimeAsync(1500);
      await vi.advanceTimersByTimeAsync(50);
      await done;
      expect(delays.length).toBeGreaterThanOrEqual(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops promptly when aborted while waiting to reconnect", async () => {
    mockFetch({ [EVENTS]: () => sseResponse([frame("ready")]) });
    const controller = new AbortController();
    const done = runEventStream({
      signal: controller.signal,
      onEvent: () => {},
      onReconnected: () => {},
      random: () => 0,
      baseDelayMs: 60_000,
    });
    setTimeout(() => controller.abort(), 30);
    await done; // resolves instead of waiting for the backoff
  });
});
