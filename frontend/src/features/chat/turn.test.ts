import { describe, expect, it } from "vitest";
import type { ChatStreamEvent } from "./stream";
import { chatReducer, initialChatState, isSuperseded, savedMessagesExpected, type ChatAction, type ChatState } from "./turn";
import type { Citation } from "./types";

const citation = (id: string): Citation => ({ chunkId: id, documentId: "d", title: `Doc ${id}`, page: null, headingPath: [] });
const stream = (event: ChatStreamEvent): ChatAction => ({ type: "stream", event });

function run(actions: ChatAction[], from: ChatState = initialChatState): ChatState {
  return actions.reduce(chatReducer, from);
}

const started = (overrides: Partial<Extract<ChatAction, { type: "started" }>> = {}): ChatAction => ({
  type: "started",
  conversationId: "c1",
  question: "How do refunds work?",
  baseCount: 0,
  wasEscalated: false,
  ...overrides,
});

describe("chat turn reducer", () => {
  it("assembles an answer from tokens, with citations once, and settles on done", () => {
    const state = run([
      started(),
      stream({ type: "token", text: "Refunds " }),
      stream({ type: "token", text: "take 5 days [1]." }),
      stream({ type: "citation", citation: citation("a") }),
      stream({ type: "citation", citation: citation("a") }),
      stream({ type: "done", status: "completed" }),
    ]);
    expect(state.turn.phase).toBe("settled");
    expect(state.turn.answer).toBe("Refunds take 5 days [1].");
    expect(state.turn.citations).toHaveLength(1);
    expect(state.turn.error).toBeNull();
  });

  it("drops the partial answer on reset and starts again", () => {
    const state = run([
      started(),
      stream({ type: "token", text: "A wrong first try" }),
      stream({ type: "reset" }),
      stream({ type: "token", text: "The grounded answer" }),
    ]);
    expect(state.turn.answer).toBe("The grounded answer");
    expect(state.turn.phase).toBe("streaming");
  });

  it("tracks tool calls and marks a started tool as completed", () => {
    const state = run([
      started(),
      stream({ type: "tool_call", tool: "get_subscription", status: "started" }),
      stream({ type: "tool_call", tool: "get_subscription", status: "completed" }),
    ]);
    expect(state.turn.tools).toEqual([{ tool: "get_subscription", status: "completed" }]);
  });

  it("pauses on an interrupt and waits for the decision", () => {
    const interrupt = { interruptId: "i1", tool: "update_billing_email", arguments: { new_email: "a@example.test" }, callId: "call_1" };
    const state = run([started(), stream({ type: "interrupt", interrupt }), stream({ type: "done", status: "interrupted" })]);
    expect(state.turn.phase).toBe("interrupted");
    expect(state.turn.interrupt).toEqual(interrupt);
  });

  it("resolves an approval into an outcome that stays in the thread notes", () => {
    const interrupt = { interruptId: "i1", tool: "update_billing_email", arguments: { new_email: "a@example.test" }, callId: null };
    const state = run([
      started({ baseCount: 2 }),
      stream({ type: "interrupt", interrupt }),
      stream({ type: "done", status: "interrupted" }),
      { type: "decision_started" },
      { type: "decision_resolved", approved: true, answer: "Your billing email is updated.", interrupt: null },
    ]);
    expect(state.turn.phase).toBe("settled");
    expect(state.turn.answer).toBe("Your billing email is updated.");
    expect(state.turn.outcome).toEqual({ approved: true, tool: "update_billing_email", arguments: { new_email: "a@example.test" } });
    expect(state.notes).toEqual([expect.objectContaining({ kind: "decision", anchor: 3 })]);
  });

  it("keeps the card when the decision call fails, and records a denial when it works", () => {
    const interrupt = { interruptId: "i1", tool: "cancel_subscription", arguments: {}, callId: null };
    const waiting = run([started(), stream({ type: "interrupt", interrupt }), stream({ type: "done", status: "interrupted" })]);
    const failed = run([{ type: "decision_started" }, { type: "decision_failed", message: "No." }], waiting);
    expect(failed.turn.phase).toBe("interrupted");
    expect(failed.turn.error).toEqual({ kind: "decision", message: "No." });
    const denied = run([{ type: "decision_started" }, { type: "decision_resolved", approved: false, answer: null, interrupt: null }], failed);
    expect(denied.turn.outcome?.approved).toBe(false);
    expect(denied.turn.phase).toBe("settled");
    expect(denied.turn.error).toBeNull();
  });

  it("goes back to waiting when the resumed turn pauses on another action", () => {
    const first = { interruptId: "i1", tool: "a", arguments: {}, callId: null };
    const second = { interruptId: "i2", tool: "b", arguments: {}, callId: null };
    const state = run([
      started(),
      stream({ type: "interrupt", interrupt: first }),
      stream({ type: "done", status: "interrupted" }),
      { type: "decision_started" },
      { type: "decision_resolved", approved: true, answer: null, interrupt: second },
    ]);
    expect(state.turn.phase).toBe("interrupted");
    expect(state.turn.interrupt?.interruptId).toBe("i2");
  });

  it("notes the handoff when the assistant escalates, but not when an agent already had the conversation", () => {
    const events: ChatAction[] = [
      stream({ type: "token", text: "I will hand you to a person." }),
      stream({ type: "escalated", ticketId: "T-9" }),
      stream({ type: "done", status: "escalated" }),
    ];
    const fresh = run([started({ baseCount: 4 }), ...events]);
    expect(fresh.turn.escalation).toEqual({ ticketId: "T-9" });
    expect(fresh.notes).toEqual([expect.objectContaining({ kind: "handoff", ticketId: "T-9", anchor: 6 })]);

    const already = run([started({ wasEscalated: true }), stream({ type: "escalated", ticketId: "T-9" }), stream({ type: "done", status: "escalated" })]);
    expect(already.notes).toEqual([]);
    expect(already.turn.answer).toBe("");
  });

  it("settles with an error frame and keeps the question for a retry", () => {
    const state = run([started(), stream({ type: "token", text: "Par" }), stream({ type: "error", message: "Failed." })]);
    expect(state.turn.phase).toBe("settled");
    expect(state.turn.error).toEqual({ kind: "stream", message: "Failed." });
    expect(state.turn.question).toBe("How do refunds work?");
  });

  it("keeps the partial text when stopped and ignores late frames", () => {
    const state = run([
      started(),
      stream({ type: "token", text: "Half an answer" }),
      { type: "stopped" },
      stream({ type: "token", text: " that must not appear" }),
    ]);
    expect(state.turn).toMatchObject({ phase: "settled", stopped: true, answer: "Half an answer" });
  });

  it("starts clean on a switch", () => {
    expect(run([started(), { type: "switched" }])).toEqual(initialChatState);
  });
});

describe("handing over to the saved messages", () => {
  const settled = (actions: ChatAction[]) => run([started({ baseCount: 2 }), ...actions]).turn;

  it("waits for the question and the answer to be saved", () => {
    const turn = settled([stream({ type: "token", text: "Answer" }), stream({ type: "done", status: "completed" })]);
    expect(savedMessagesExpected(turn)).toBe(4);
    expect(isSuperseded(turn, 3)).toBe(false);
    expect(isSuperseded(turn, 4)).toBe(true);
  });

  it("needs only the customer message for a handoff turn without an answer", () => {
    const turn = run([started({ baseCount: 2, wasEscalated: true }), stream({ type: "done", status: "escalated" })]).turn;
    expect(isSuperseded(turn, 3)).toBe(true);
  });

  it("expects the answer of a stopped turn, since the server finishes it", () => {
    const turn = settled([stream({ type: "token", text: "Half" }), { type: "stopped" }]);
    expect(isSuperseded(turn, 3)).toBe(false);
    expect(isSuperseded(turn, 4)).toBe(true);
  });

  it("never replaces a failed turn on its own", () => {
    expect(isSuperseded(settled([stream({ type: "error", message: "Failed." })]), 99)).toBe(false);
  });

  it("does not replace a turn that is still running", () => {
    expect(isSuperseded(settled([stream({ type: "token", text: "x" })]), 99)).toBe(false);
  });
});
