import { vi } from "vitest";
import type { Session } from "@/api/types";

/** A runtime-generated placeholder that is shaped like a token but is never a real one. */
export function fakeToken(label: string): string {
  return `test-${label}-${crypto.randomUUID()}`;
}

export function fakeSession(accessToken: string, role: Session["user"]["role"] = "user"): Session {
  return {
    access_token: accessToken,
    token_type: "bearer",
    expires_in: 900,
    user: { id: crypto.randomUUID(), email: "person@example.test", role, status: "active" },
    workspace: { id: crypto.randomUUID(), name: "Example Workspace", slug: "example" },
  };
}

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export type Handler = (request: { url: string; init: RequestInit; headers: Headers }) => Response | Promise<Response>;

/** Replace global fetch with a router keyed by "METHOD /path". Returns the mock for call inspection. */
export function mockFetch(routes: Record<string, Handler | Handler[]>) {
  const queues = new Map<string, Handler[]>();
  for (const [key, value] of Object.entries(routes)) queues.set(key, Array.isArray(value) ? [...value] : [value]);
  const mock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const key = `${(init.method ?? "GET").toUpperCase()} ${url}`;
    const queue = queues.get(key);
    if (!queue || queue.length === 0) throw new Error(`Unexpected request: ${key}`);
    const handler = queue.length > 1 ? queue.shift()! : queue[0]!;
    if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const response = await handler({ url, init, headers: new Headers(init.headers) });
    return init.signal && response.body ? abortable(response, init.signal) : response;
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** Make a response body fail with AbortError when the request signal aborts, as a real network stream does. */
function abortable(response: Response, signal: AbortSignal): Response {
  const reader = response.body!.getReader();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      signal.addEventListener(
        "abort",
        () => {
          try {
            controller.error(new DOMException("Aborted", "AbortError"));
          } catch {
            // already closed
          }
        },
        { once: true },
      );
    },
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) controller.close();
      else controller.enqueue(value);
    },
    cancel: (reason) => reader.cancel(reason),
  });
  return new Response(stream, { status: response.status, headers: response.headers });
}

export function callsTo(mock: ReturnType<typeof mockFetch>, key: string) {
  return mock.mock.calls.filter(([input, init]) => `${((init as RequestInit)?.method ?? "GET").toUpperCase()} ${String(input)}` === key);
}

/** An SSE response whose body delivers the given frames, then ends (or stays open when `hold` is set). */
export function sseResponse(frames: string[], options: { hold?: boolean; status?: number } = {}): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      if (!options.hold) controller.close();
    },
  });
  return new Response(stream, { status: options.status ?? 200, headers: { "Content-Type": "text/event-stream" } });
}

export function frame(event: string, data: unknown = {}): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}
