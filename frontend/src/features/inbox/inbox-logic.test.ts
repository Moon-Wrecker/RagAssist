import { describe, expect, it } from "vitest";
import type { ConversationDetail, EscalationSummary } from "@/api/escalations";
import {
  canSendReply,
  countByFilter,
  filterEscalations,
  filterFor,
  parseMessages,
  replyBlockedReason,
  sortEscalations,
  withPendingReply,
  withResolved,
} from "./inbox-logic";

function item(id: string, status: string, updated: string, summary = `Question ${id}`): EscalationSummary {
  return {
    escalation_id: id,
    tenant_id: "t",
    status,
    summary,
    priority: "high",
    created_at: updated,
    updated_at: updated,
  };
}

const items = [
  item("a", "resolved", "2030-01-03T10:00:00Z", "Invoice is wrong"),
  item("b", "escalated", "2030-01-01T10:00:00Z", "Cannot log in"),
  item("c", "escalated", "2030-01-02T10:00:00Z", "Refund for order"),
  item("d", "resolved", "2030-01-04T10:00:00Z", "Password reset"),
];

describe("sorting and filtering", () => {
  it("puts open conversations first, newest activity first inside each group", () => {
    expect(sortEscalations(items).map((i) => i.escalation_id)).toEqual(["c", "b", "d", "a"]);
  });

  it("does not reorder or mutate the input", () => {
    const copy = [...items];
    sortEscalations(items);
    expect(items).toEqual(copy);
  });

  it("filters by state", () => {
    expect(filterEscalations(items, "needs-reply", "").map((i) => i.escalation_id)).toEqual(["c", "b"]);
    expect(filterEscalations(items, "resolved", "").map((i) => i.escalation_id)).toEqual(["d", "a"]);
    expect(filterEscalations(items, "all", "")).toHaveLength(4);
  });

  it("searches summaries without caring about case or surrounding spaces", () => {
    expect(filterEscalations(items, "all", "  REFUND ").map((i) => i.escalation_id)).toEqual(["c"]);
    expect(filterEscalations(items, "needs-reply", "invoice")).toEqual([]);
  });

  it("counts each filter", () => {
    expect(countByFilter(items)).toEqual({ "needs-reply": 2, resolved: 2, all: 4 });
    expect(countByFilter([])).toEqual({ "needs-reply": 0, resolved: 0, all: 0 });
  });

  it("opens a resolved conversation on the resolved filter", () => {
    expect(filterFor(items[0])).toBe("resolved");
    expect(filterFor(items[1])).toBe("needs-reply");
    expect(filterFor(undefined)).toBe("needs-reply");
  });
});

describe("parseMessages", () => {
  it("maps API roles to labels, keeps order, and drops empty text", () => {
    const messages = parseMessages([
      { role: "user", text: "Help", created_at: "2030-01-01T10:00:00Z" },
      { role: "assistant", text: "I could not find that.", created_at: "2030-01-01T10:00:05Z" },
      { role: "agent", content: "Looking now", created_at: "2030-01-01T10:05:00Z" },
      { role: "user", text: "   " },
      { role: "tool", text: "x" },
    ]);
    expect(messages.map((m) => [m.role, m.text])).toEqual([
      ["customer", "Help"],
      ["assistant", "I could not find that."],
      ["agent", "Looking now"],
      ["other", "x"],
    ]);
    expect(new Set(messages.map((m) => m.key)).size).toBe(messages.length);
  });

  it("copes with a missing list and marks pending replies", () => {
    expect(parseMessages(undefined)).toEqual([]);
    expect(parseMessages([{ role: "agent", text: "On it", pending: true }])[0]?.pending).toBe(true);
  });
});

describe("optimistic updates", () => {
  const detail: ConversationDetail = {
    conversation_id: "b",
    tenant_id: "t",
    title: "Cannot log in",
    status: "escalated",
    messages: [{ role: "user", text: "Help", created_at: "2030-01-01T10:00:00Z" }],
    created_at: "2030-01-01T10:00:00Z",
    updated_at: "2030-01-01T10:00:00Z",
  };

  it("appends a pending agent reply without touching the original", () => {
    const next = withPendingReply(detail, "Try again now", new Date("2030-01-01T10:06:00Z"));
    expect(next.messages).toHaveLength(2);
    expect(next.messages?.[1]).toMatchObject({ role: "agent", text: "Try again now", pending: true });
    expect(detail.messages).toHaveLength(1);
  });

  it("marks only the named conversation resolved", () => {
    const list = { items, total: 4 };
    const next = withResolved(list, "b", new Date("2030-02-01T00:00:00Z"));
    expect(next.items.find((i) => i.escalation_id === "b")?.status).toBe("resolved");
    expect(next.items.find((i) => i.escalation_id === "c")?.status).toBe("escalated");
    expect(list.items.find((i) => i.escalation_id === "b")?.status).toBe("escalated");
    expect(withResolved(list, "missing").items).toEqual(items);
  });
});

describe("reply rules", () => {
  it("allows a reply only from an agent, on an escalated thread, with text, when idle", () => {
    const base = { status: "escalated", text: "Hello", role: "agent", sending: false };
    expect(canSendReply(base)).toBe(true);
    expect(canSendReply({ ...base, text: "   " })).toBe(false);
    expect(canSendReply({ ...base, status: "resolved" })).toBe(false);
    expect(canSendReply({ ...base, role: "admin" })).toBe(false);
    expect(canSendReply({ ...base, sending: true })).toBe(false);
  });

  it("explains why a reply is blocked, in plain words", () => {
    expect(replyBlockedReason({ status: "resolved", role: "agent" })).toMatch(/resolved/);
    expect(replyBlockedReason({ status: "escalated", role: "admin" })).toMatch(/Only support agents/);
    expect(replyBlockedReason({ status: "escalated", role: "agent" })).toBeNull();
  });
});
