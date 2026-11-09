import { createParser } from "eventsource-parser";
import { apiFetch, notifySessionLost, refreshSession } from "@/api/http";
import type { LiveEvent } from "./invalidation";

/**
 * Fetch-based reader for `GET /v1/events`. `EventSource` cannot send the bearer token, so the stream is read
 * with `fetch` and parsed with eventsource-parser.
 *
 * Lifecycle (docs/api/sse-contract.md):
 * - `ready` opens every connection. There is no replay, so after any reconnect the caller invalidates everything.
 * - `resync` means the server may have dropped events; the caller invalidates everything. The stream stays open.
 * - `reauth` means the access token expired and the server is closing the stream: refresh, reconnect at once.
 * - Any other end or failure reconnects with exponential backoff and jitter. A silent connection (no frame or
 *   15-second ping for `idleTimeoutMs`) is treated as dead.
 */
export interface EventStreamOptions {
  onEvent: (event: LiveEvent) => void;
  /** Called on every `ready` after the first one: events may have been missed, so refetch everything. */
  onReconnected: () => void;
  onStatus?: (status: "connecting" | "connected" | "reconnecting") => void;
  signal: AbortSignal;
  baseDelayMs?: number;
  maxDelayMs?: number;
  idleTimeoutMs?: number;
  /** Replaceable in tests. */
  random?: () => number;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

const DEFAULTS = { baseDelayMs: 1_000, maxDelayMs: 30_000, idleTimeoutMs: 45_000 } as const;

export function backoffDelay(attempt: number, base: number, max: number, random: () => number): number {
  const ceiling = Math.min(max, base * 2 ** attempt);
  // Full jitter keeps a fleet of clients from reconnecting in lockstep after an API restart.
  return Math.round(ceiling / 2 + (ceiling / 2) * random());
}

function sleepUnlessAborted(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const timer = setTimeout(done, ms);
    function done() {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    }
    signal.addEventListener("abort", done, { once: true });
  });
}

function parseData(raw: string): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(raw);
    return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

type EndReason = "reauth" | "ended";

/** Reads one connection until it ends. Resolves with why it ended; rejects on network or HTTP failure. */
async function readOnce(options: EventStreamOptions, onReady: () => void, idleTimeoutMs: number): Promise<EndReason> {
  const connection = new AbortController();
  const stop = () => connection.abort();
  options.signal.addEventListener("abort", stop, { once: true });
  let idle: ReturnType<typeof setTimeout> | undefined;
  const armIdle = () => {
    clearTimeout(idle);
    idle = setTimeout(stop, idleTimeoutMs);
  };

  try {
    armIdle();
    const response = await apiFetch("/v1/events", {
      headers: { Accept: "text/event-stream", "Cache-Control": "no-cache" },
      signal: connection.signal,
      cache: "no-store",
      retryOnUnauthorized: true,
    });
    if (response.status === 401) throw new SessionEnded();
    if (!response.ok || !response.body) throw new Error(`Event stream refused with status ${response.status}`);

    let reason: EndReason = "ended";
    const parser = createParser({
      onEvent: (message) => {
        const type = message.event ?? "message";
        if (type === "ready") onReady();
        if (type === "reauth") reason = "reauth";
        options.onEvent({ type, data: parseData(message.data) });
      },
    });
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      armIdle();
      parser.feed(value);
    }
    return reason;
  } finally {
    clearTimeout(idle);
    options.signal.removeEventListener("abort", stop);
    connection.abort();
  }
}

class SessionEnded extends Error {}

/** Runs until `options.signal` aborts or the session ends. Never rejects. */
export async function runEventStream(options: EventStreamOptions): Promise<void> {
  const {
    signal,
    baseDelayMs = DEFAULTS.baseDelayMs,
    maxDelayMs = DEFAULTS.maxDelayMs,
    idleTimeoutMs = DEFAULTS.idleTimeoutMs,
    random = Math.random,
    sleep = sleepUnlessAborted,
  } = options;
  let attempt = 0;
  let everReady = false;

  while (!signal.aborted) {
    options.onStatus?.(everReady ? "reconnecting" : "connecting");
    let reason: EndReason = "ended";
    try {
      reason = await readOnce(
        options,
        () => {
          attempt = 0;
          options.onStatus?.("connected");
          if (everReady) options.onReconnected();
          everReady = true;
        },
        idleTimeoutMs,
      );
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof SessionEnded) return;
    }
    if (signal.aborted) return;

    if (reason === "reauth") {
      try {
        const session = await refreshSession();
        if (!session) {
          notifySessionLost();
          return;
        }
        // A fresh token: reconnect immediately, no backoff.
        continue;
      } catch {
        // The refresh could not reach the server; fall through to the backoff below.
      }
    }

    await sleep(backoffDelay(attempt, baseDelayMs, maxDelayMs, random), signal);
    attempt += 1;
  }
}
