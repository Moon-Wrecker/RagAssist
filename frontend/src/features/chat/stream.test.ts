import { describe, expect, it } from "vitest";
import { parseChatFrame, readChatStream, type ChatStreamEvent } from "./stream";

describe("parseChatFrame", () => {
  it("reads every event of the contract", () => {
    expect(parseChatFrame("token", '{"text":"Hello"}')).toEqual({ type: "token", text: "Hello" });
    expect(parseChatFrame("token", '{"text":"","reset":true}')).toEqual({ type: "reset" });
    expect(
      parseChatFrame("citation", '{"chunk_id":"c1","document_id":"d1","title":"Billing FAQ","page":3,"heading_path":["Billing","Refunds"]}'),
    ).toEqual({
      type: "citation",
      citation: { chunkId: "c1", documentId: "d1", title: "Billing FAQ", page: 3, headingPath: ["Billing", "Refunds"] },
    });
    expect(parseChatFrame("tool_call", '{"tool":"get_subscription","arguments":{}}')).toEqual({
      type: "tool_call",
      tool: "get_subscription",
      status: "started",
    });
    expect(parseChatFrame("tool_call", '{"tool":"get_subscription","status":"completed"}')).toMatchObject({ status: "completed" });
    expect(
      parseChatFrame(
        "interrupt",
        '{"interrupt_id":"i1","action":"approval_required","tool":"update_email","arguments":{"new_email":"a@example.test"},"call_id":"call_1"}',
      ),
    ).toEqual({
      type: "interrupt",
      interrupt: { interruptId: "i1", tool: "update_email", arguments: { new_email: "a@example.test" }, callId: "call_1" },
    });
    expect(parseChatFrame("escalated", '{"ticket_id":"T-1","status":"open","priority":"high"}')).toEqual({ type: "escalated", ticketId: "T-1" });
    expect(parseChatFrame("done", '{"conversation_id":"x","status":"interrupted"}')).toEqual({ type: "done", status: "interrupted" });
    expect(parseChatFrame("error", '{"code":"internal_error","message":"Nope."}')).toEqual({ type: "error", message: "Nope." });
  });

  it("drops unknown events and malformed payloads instead of throwing", () => {
    expect(parseChatFrame("future_event", "{}")).toBeNull();
    expect(parseChatFrame(undefined, '{"text":"x"}')).toBeNull();
    expect(parseChatFrame("token", "not json")).toBeNull();
    expect(parseChatFrame("token", "[1]")).toBeNull();
    expect(parseChatFrame("citation", '{"title":"no id"}')).toBeNull();
    expect(parseChatFrame("interrupt", '{"tool":"x"}')).toBeNull();
  });
});

function bodyOf(chunks: string[]): ReadableStream<Uint8Array<ArrayBuffer>> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk) as Uint8Array<ArrayBuffer>);
      controller.close();
    },
  });
}

describe("readChatStream", () => {
  it("reassembles frames split across chunks and ignores ping comments", async () => {
    const events: ChatStreamEvent[] = [];
    await readChatStream(
      bodyOf([
        'event: token\ndata: {"te',
        'xt":"Hel"}\n\n: ping\n\nevent: token\ndata: {"text":"lo"}\n\n',
        'event: done\ndata: {"conversation_id":"c","status":"completed"}\n\n',
      ]),
      (event) => events.push(event),
    );
    expect(events).toEqual([
      { type: "token", text: "Hel" },
      { type: "token", text: "lo" },
      { type: "done", status: "completed" },
    ]);
  });

  it("rejects when the body fails mid-stream, so the caller can tell a drop from a finish", async () => {
    let pulls = 0;
    const body = new ReadableStream<Uint8Array<ArrayBuffer>>({
      pull(controller) {
        pulls += 1;
        if (pulls === 1) {
          controller.enqueue(new TextEncoder().encode('event: token\ndata: {"text":"a"}\n\n') as Uint8Array<ArrayBuffer>);
        } else {
          controller.error(new DOMException("Aborted", "AbortError"));
        }
      },
    });
    const events: ChatStreamEvent[] = [];
    await expect(readChatStream(body, (event) => events.push(event))).rejects.toMatchObject({ name: "AbortError" });
    expect(events).toEqual([{ type: "token", text: "a" }]);
  });
});
