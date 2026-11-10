import type { ConversationDetail, EscalationSummary } from "@/api/escalations";

/** Pure list, filter and optimistic-update logic for the inbox. No React, no network. */

export type InboxFilter = "needs-reply" | "resolved" | "all";

export const FILTER_LABELS: Record<InboxFilter, string> = {
  "needs-reply": "Needs a reply",
  resolved: "Resolved",
  all: "All",
};

export function isOpen(item: Pick<EscalationSummary, "status">): boolean {
  return item.status === "escalated";
}

function byRecentActivity(a: EscalationSummary, b: EscalationSummary): number {
  return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
}

/** Open conversations first (they are what the agent is here for), newest activity first inside each group. */
export function sortEscalations(items: readonly EscalationSummary[]): EscalationSummary[] {
  const open = items.filter(isOpen).sort(byRecentActivity);
  const rest = items.filter((item) => !isOpen(item)).sort(byRecentActivity);
  return [...open, ...rest];
}

export function filterEscalations(
  items: readonly EscalationSummary[],
  filter: InboxFilter,
  query: string,
): EscalationSummary[] {
  const needle = query.trim().toLowerCase();
  return sortEscalations(items).filter((item) => {
    if (filter === "needs-reply" && !isOpen(item)) return false;
    if (filter === "resolved" && isOpen(item)) return false;
    return needle === "" || item.summary.toLowerCase().includes(needle);
  });
}

export function countByFilter(items: readonly EscalationSummary[]): Record<InboxFilter, number> {
  const open = items.filter(isOpen).length;
  return { "needs-reply": open, resolved: items.length - open, all: items.length };
}

/** Which filter shows a given conversation, so a deep link to a resolved one does not look empty. */
export function filterFor(item: Pick<EscalationSummary, "status"> | undefined): InboxFilter {
  return item && !isOpen(item) ? "resolved" : "needs-reply";
}

// --- messages -------------------------------------------------------------------------------------------------

export type MessageRole = "customer" | "assistant" | "agent" | "other";

export interface ThreadMessage {
  /** Stable enough for React keys: position plus timestamp. */
  key: string;
  role: MessageRole;
  text: string;
  createdAt: string;
  /** True while an agent reply is on its way to the server and has not been confirmed. */
  pending: boolean;
}

export const ROLE_LABELS: Record<MessageRole, string> = {
  customer: "Customer",
  assistant: "Assistant",
  agent: "Support agent",
  other: "Message",
};

function roleOf(raw: unknown): MessageRole {
  switch (raw) {
    case "user":
    case "customer":
      return "customer";
    case "assistant":
      return "assistant";
    case "agent":
      return "agent";
    default:
      return "other";
  }
}

/** The API sends loosely typed message objects; this reads them defensively and drops what has no text. */
export function parseMessages(raw: readonly Record<string, unknown>[] | undefined): ThreadMessage[] {
  const messages: ThreadMessage[] = [];
  (raw ?? []).forEach((entry, index) => {
    const text = typeof entry.text === "string" ? entry.text : typeof entry.content === "string" ? entry.content : "";
    if (text.trim() === "") return;
    const createdAt = typeof entry.created_at === "string" ? entry.created_at : "";
    messages.push({
      key: `${index}-${createdAt}`,
      role: roleOf(entry.role),
      text,
      createdAt,
      pending: entry.pending === true,
    });
  });
  return messages;
}

// --- optimistic updates ---------------------------------------------------------------------------------------

/** The thread with an agent reply appended and marked pending. Never mutates its input. */
export function withPendingReply(detail: ConversationDetail, text: string, now: Date = new Date()): ConversationDetail {
  const reply = { role: "agent", text, created_at: now.toISOString(), pending: true };
  return { ...detail, messages: [...(detail.messages ?? []), reply] };
}

/** The list with one conversation marked resolved. An id that is not in the list changes nothing. */
export function withResolved(
  list: { items: EscalationSummary[]; total: number },
  id: string,
  now: Date = new Date(),
): { items: EscalationSummary[]; total: number } {
  return {
    ...list,
    items: list.items.map((item) =>
      item.escalation_id === id ? { ...item, status: "resolved", updated_at: now.toISOString() } : item,
    ),
  };
}

export function withThreadResolved(detail: ConversationDetail): ConversationDetail {
  return { ...detail, status: "resolved" };
}

/** A reply can only be sent by an agent, while the conversation is escalated, with text, and when idle. */
export function canSendReply(args: { status: string; text: string; role: string; sending: boolean }): boolean {
  return args.role === "agent" && args.status === "escalated" && args.text.trim() !== "" && !args.sending;
}

export function replyBlockedReason(args: { status: string; role: string }): string | null {
  if (args.status !== "escalated") {
    return "This conversation is resolved.";
  }
  if (args.role !== "agent") return "Only support agents can reply.";
  return null;
}
