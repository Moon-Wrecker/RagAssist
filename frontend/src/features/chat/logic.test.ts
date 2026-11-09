import { describe, expect, it } from "vitest";
import { argumentRows } from "./argument-rows";
import { composerState, isHandoff } from "./composer-state";
import { filterConversations } from "./filter-conversations";
import { parseMessages } from "./messages";
import { sourceLocation } from "./source-location";
import { buildThread } from "./thread";
import { idleTurn, type ThreadNote, type TurnState } from "./turn";
import { titleFrom } from "./use-chat";
import type { ChatMessage, ConversationSummary } from "./types";

const message = (id: string, role: ChatMessage["role"], text: string): ChatMessage => ({ id, role, text, citations: [], createdAt: null });
const turn = (overrides: Partial<TurnState>): TurnState => ({ ...idleTurn, ...overrides });

describe("parseMessages", () => {
  it("keeps user, assistant and agent turns with text and their citations", () => {
    const parsed = parseMessages([
      { role: "user", text: "Hi", created_at: "2026-01-01T10:00:00Z" },
      { role: "assistant", text: "Answer [1]", citations: [{ chunk_id: "c1", title: "Doc", page: 2, heading_path: ["A"] }, { title: "bad" }] },
      { role: "agent", text: "A person here" },
      { role: "system", text: "hidden" },
      { role: "assistant", text: "" },
    ]);
    expect(parsed.map((m) => m.role)).toEqual(["user", "assistant", "agent"]);
    expect(parsed[1]?.citations).toEqual([{ chunkId: "c1", documentId: "", title: "Doc", page: 2, headingPath: ["A"] }]);
  });
});

describe("buildThread", () => {
  const saved = [message("m0", "user", "q1"), message("m1", "assistant", "a1")];

  it("shows saved messages with notes in place when no turn is live", () => {
    const notes: ThreadNote[] = [{ id: "n", anchor: 1, kind: "handoff", ticketId: "T-1" }];
    const items = buildThread(saved, notes, idleTurn);
    expect(items.map((i) => i.kind)).toEqual(["message", "note", "message"]);
  });

  it("puts a note whose anchor is past the end after the last message", () => {
    const notes: ThreadNote[] = [{ id: "n", anchor: 2, kind: "handoff", ticketId: null }];
    expect(buildThread(saved, notes, idleTurn).map((i) => i.kind)).toEqual(["message", "message", "note"]);
  });

  it("hides what the live turn already shows, so a refetch mid-stream does not repeat the question", () => {
    const live = turn({ phase: "streaming", baseCount: 2, question: "q2", answer: "partial" });
    const withEcho = [...saved, message("m2", "user", "q2")];
    const items = buildThread(withEcho, [], live);
    expect(items.map((i) => i.kind)).toEqual(["message", "message", "live"]);
  });

  it("gives way to the saved messages once they hold the answer", () => {
    const done = turn({ phase: "settled", baseCount: 2, question: "q2", answer: "a2" });
    const all = [...saved, message("m2", "user", "q2"), message("m3", "assistant", "a2")];
    expect(buildThread(all, [], done).map((i) => i.kind)).toEqual(["message", "message", "message", "message"]);
    expect(buildThread([...saved, message("m2", "user", "q2")], [], done).at(-1)?.kind).toBe("live");
  });

  it("keeps a failed turn visible", () => {
    const failed = turn({ phase: "settled", baseCount: 2, question: "q2", error: { kind: "stream", message: "x" } });
    expect(buildThread([...saved, message("m2", "user", "q2")], [], failed).at(-1)?.kind).toBe("live");
  });
});

describe("composer state: approval and handoff", () => {
  it("is free when idle and when a turn has settled", () => {
    expect(composerState("open", idleTurn)).toMatchObject({ lockedFor: null, canStop: false, audience: "assistant" });
    expect(composerState("open", turn({ phase: "settled" })).lockedFor).toBeNull();
  });

  it("offers Stop and locks while streaming", () => {
    expect(composerState("open", turn({ phase: "streaming" }))).toMatchObject({ lockedFor: "streaming", canStop: true });
  });

  it("locks while an approval is pending and while the decision is sent, without Stop", () => {
    expect(composerState("open", turn({ phase: "interrupted" }))).toMatchObject({ lockedFor: "approval", canStop: false });
    expect(composerState("open", turn({ phase: "deciding" }))).toMatchObject({ lockedFor: "deciding", canStop: false });
  });

  it("sends to the agent while the conversation is escalated, and back to the assistant once resolved", () => {
    expect(isHandoff("escalated")).toBe(true);
    expect(isHandoff("resolved")).toBe(false);
    expect(isHandoff(undefined)).toBe(false);
    expect(composerState("escalated", idleTurn)).toMatchObject({ audience: "agent", lockedFor: null });
    expect(composerState("escalated", idleTurn).label).toMatch(/support agent/i);
    expect(composerState("resolved", idleTurn).audience).toBe("assistant");
  });
});

describe("argumentRows", () => {
  it("shows each argument exactly, with structured values as JSON", () => {
    expect(argumentRows({ new_email: "a@example.test", count: 3, flags: { x: true } })).toEqual([
      { name: "new_email", value: "a@example.test", block: false },
      { name: "count", value: "3", block: false },
      { name: "flags", value: '{\n  "x": true\n}', block: true },
    ]);
  });

  it("handles no arguments and non-object arguments", () => {
    expect(argumentRows({})).toEqual([]);
    expect(argumentRows(null)).toEqual([]);
    expect(argumentRows(undefined)).toEqual([]);
    expect(argumentRows(["a"])).toEqual([{ name: "arguments", value: '[\n  "a"\n]', block: true }]);
  });
});

describe("small helpers", () => {
  it("sourceLocation joins the heading path and the page", () => {
    expect(sourceLocation({ headingPath: ["Billing", "Refunds"], page: 3 })).toBe("Billing / Refunds  ·  p. 3");
    expect(sourceLocation({ headingPath: [], page: null })).toBe("");
  });

  it("titleFrom takes the first line and shortens long ones", () => {
    expect(titleFrom("  How do refunds work?\nMore detail")).toBe("How do refunds work?");
    expect(titleFrom("   ")).toBe("New conversation");
    const long = titleFrom("x".repeat(200));
    expect(long.length).toBeLessThanOrEqual(60);
    expect(long.endsWith("…")).toBe(true);
  });

  it("filterConversations matches titles only, ignoring case", () => {
    const item = (id: string, title: string): ConversationSummary => ({
      conversation_id: id,
      tenant_id: "t",
      title,
      status: "open",
      messages_count: 0,
      created_at: "",
      updated_at: "",
    });
    const items = [item("1", "Refund question"), item("2", "Login problem")];
    expect(filterConversations(items, "REFUND").map((i) => i.conversation_id)).toEqual(["1"]);
    expect(filterConversations(items, "  ")).toHaveLength(2);
  });
});
