import { createParser } from "eventsource-parser";
import { parseCitation } from "./messages";
import type { Citation, PendingInterrupt } from "./types";

/**
 * The chat stream from `POST /v1/conversations/{id}/messages` (docs/api/sse-contract.md), as typed events.
 * Frames of an unknown type or with a malformed payload are dropped, so a newer server cannot break an older client.
 */
export type ChatStreamEvent =
  | { type: "token"; text: string }
  | { type: "reset" }
  | { type: "citation"; citation: Citation }
  | { type: "tool_call"; tool: string; status: "started" | "completed" }
  | { type: "interrupt"; interrupt: PendingInterrupt }
  | { type: "escalated"; ticketId: string | null }
  | { type: "done"; status: string }
  | { type: "error"; message: string };

function parseJson(raw: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(raw);
    return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Turns one SSE frame into an event, or null when the frame is not one this client understands. */
export function parseChatFrame(eventName: string | undefined, rawData: string): ChatStreamEvent | null {
  const data = parseJson(rawData);
  if (!data) return null;
  switch (eventName) {
    case "token":
      if (data.reset === true) return { type: "reset" };
      return typeof data.text === "string" && data.text !== "" ? { type: "token", text: data.text } : null;
    case "citation": {
      const citation = parseCitation(data);
      return citation ? { type: "citation", citation } : null;
    }
    case "tool_call":
      return typeof data.tool === "string"
        ? { type: "tool_call", tool: data.tool, status: data.status === "completed" ? "completed" : "started" }
        : null;
    case "interrupt": {
      const id = data.interrupt_id;
      if (typeof id !== "string" || id === "" || typeof data.tool !== "string") return null;
      return {
        type: "interrupt",
        interrupt: {
          interruptId: id,
          tool: data.tool,
          arguments: data.arguments ?? {},
          callId: typeof data.call_id === "string" ? data.call_id : null,
        },
      };
    }
    case "escalated":
      return { type: "escalated", ticketId: typeof data.ticket_id === "string" ? data.ticket_id : null };
    case "done":
      return { type: "done", status: typeof data.status === "string" ? data.status : "completed" };
    case "error":
      return {
        type: "error",
        message: typeof data.message === "string" && data.message !== "" ? data.message : "Something went wrong.",
      };
    default:
      return null;
  }
}

/**
 * Reads a chat stream to its end, calling `onEvent` per frame. Resolves when the body ends; rejects if the read
 * fails, including with an AbortError when the request's own signal aborts (the caller treats that as Stop).
 */
export async function readChatStream(
  body: ReadableStream<Uint8Array<ArrayBuffer>>,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const parser = createParser({
    onEvent: (message) => {
      const event = parseChatFrame(message.event, message.data);
      if (event) onEvent(event);
    },
  });
  const reader = body.pipeThrough(new TextDecoderStream()).getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.feed(value);
    }
  } finally {
    reader.releaseLock();
  }
}
