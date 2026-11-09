import { randomUUID } from "node:crypto";
import type { Page, Route } from "@playwright/test";

/**
 * A small in-memory stand-in for the conversation endpoints, registered on top of `mockApi` (Playwright runs the
 * most recently registered matching route first, and anything not handled here falls back to it). No backend runs.
 * It behaves like the real one where the UI depends on it: the customer message is saved when a message arrives,
 * the assistant message when the turn ends, and a stopped request does not stop the turn.
 */
export interface MockMessage {
  role: "user" | "assistant" | "agent";
  text: string;
  citations?: unknown[];
  created_at: string;
}

export interface MockConversation {
  conversation_id: string;
  title: string;
  status: "open" | "escalated" | "resolved";
  messages: MockMessage[];
  updated_at: string;
}

export interface Scripted {
  /** SSE frames to deliver, in order. */
  frames: string[];
  /** What the server saves as the assistant message when the turn ends. */
  save?: { text: string; citations?: unknown[] };
  /** The conversation status after the turn. */
  status?: MockConversation["status"];
  /** Keep the request open until `finishHeld()` (a long answer the person stops waiting for). */
  hold?: boolean;
}

export const frame = (event: string, data: unknown = {}) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

export const passage = {
  chunk_id: "chunk-refunds",
  document_id: "doc-billing",
  document_title: "Billing FAQ",
  title: "Refunds",
  text: "Refunds are issued to the original payment method within 5 business days of approval.",
  page: 3,
  heading_path: ["Billing", "Refunds"],
  is_global: false,
};

export const citation = {
  chunk_id: passage.chunk_id,
  document_id: passage.document_id,
  title: passage.document_title,
  page: passage.page,
  heading_path: passage.heading_path,
};

export interface ChatMock {
  conversations: MockConversation[];
  /** Decide what the next message gets as an answer. */
  script: (next: (content: string, conversation: MockConversation) => Scripted) => void;
  /** Add a conversation to history before the page loads. */
  seed: (conversation: Partial<MockConversation> & { title: string }) => MockConversation;
  /** Deliver a live event to the page (the open `GET /v1/events` request answers with it). */
  pushEvent: (type: string, data: Record<string, unknown>) => void;
  /** Finish a held turn: the server saves the answer although the client stopped watching. */
  finishHeld: () => void;
  /** The bodies of `POST .../actions/...` calls. */
  decisions: { interruptId: string; approved: unknown }[];
  /** Bodies of `POST .../messages` calls. */
  sent: string[];
}

const json = (route: Route, status: number, body: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

const now = () => new Date().toISOString();

export async function mockChat(page: Page): Promise<ChatMock> {
  const conversations: MockConversation[] = [];
  const decisions: ChatMock["decisions"] = [];
  const sent: string[] = [];
  let next: Parameters<ChatMock["script"]>[0] = () => ({ frames: [frame("done", { status: "completed" })] });
  let release: (() => void) | null = null;
  let eventWaiter: ((body: string) => void) | null = null;
  const queuedEvents: string[] = [];

  const summary = (c: MockConversation) => ({
    conversation_id: c.conversation_id,
    tenant_id: "tenant-example",
    title: c.title,
    status: c.status,
    messages_count: c.messages.length,
    created_at: c.updated_at,
    updated_at: c.updated_at,
  });

  const mock: ChatMock = {
    conversations,
    decisions,
    sent,
    script: (fn) => {
      next = fn;
    },
    seed: (partial) => {
      const conversation: MockConversation = {
        conversation_id: randomUUID(),
        status: "open",
        messages: [],
        updated_at: now(),
        ...partial,
      };
      conversations.unshift(conversation);
      return conversation;
    },
    pushEvent: (type, data) => {
      const body = frame(type, data);
      if (eventWaiter) {
        eventWaiter(body);
        eventWaiter = null;
      } else queuedEvents.push(body);
    },
    finishHeld: () => release?.(),
  };

  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (method === "GET" && path === "/v1/events") {
      // One connection at a time: answer when an event is pushed, then the client reconnects (and refetches).
      const body = queuedEvents.length > 0 ? queuedEvents.splice(0).join("") : await new Promise<string>((resolve) => (eventWaiter = resolve));
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: frame("ready") + body }).catch(() => {});
    }
    if (method === "GET" && path === "/v1/conversations") {
      return json(route, 200, { items: conversations.map(summary), total: conversations.length });
    }
    if (method === "POST" && path === "/v1/conversations") {
      const created = mock.seed({ title: (request.postDataJSON() as { title?: string }).title ?? "New Conversation" });
      return json(route, 201, summary(created));
    }
    const detail = path.match(/^\/v1\/conversations\/([^/]+)$/);
    if (method === "GET" && detail) {
      const found = conversations.find((c) => c.conversation_id === detail[1]);
      if (!found) return json(route, 404, { detail: "Conversation not found" });
      return json(route, 200, { ...summary(found), messages: found.messages });
    }
    const messages = path.match(/^\/v1\/conversations\/([^/]+)\/messages$/);
    if (method === "POST" && messages) {
      const found = conversations.find((c) => c.conversation_id === messages[1]);
      if (!found) return json(route, 404, { detail: "Conversation not found" });
      const content = (request.postDataJSON() as { content: string }).content;
      sent.push(content);
      found.messages.push({ role: "user", text: content, created_at: now() });
      const turn = next(content, found);
      const finish = () => {
        if (turn.save) found.messages.push({ role: "assistant", text: turn.save.text, citations: turn.save.citations ?? [], created_at: now() });
        if (turn.status) found.status = turn.status;
        found.updated_at = now();
        mock.pushEvent("message.created", { conversation_id: found.conversation_id });
      };
      if (turn.hold) {
        await new Promise<void>((resolve) => (release = resolve));
        finish();
        return route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }).catch(() => {});
      }
      finish();
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: turn.frames.join("") });
    }
    const action = path.match(/^\/v1\/conversations\/([^/]+)\/actions\/([^/]+)$/);
    if (method === "POST" && action) {
      const body = request.postDataJSON() as { approved: unknown };
      decisions.push({ interruptId: action[2] ?? "", approved: body.approved });
      const found = conversations.find((c) => c.conversation_id === action[1]);
      const answer = body.approved ? "Done. Your billing email is now updated." : "Understood. I did not change anything.";
      found?.messages.push({ role: "assistant", text: answer, created_at: now() });
      return json(route, 200, {
        conversation_id: action[1],
        interrupt_id: action[2],
        approved: body.approved,
        status: "resumed",
        answer,
        interrupt: null,
      });
    }
    const chunk = path.match(/^\/v1\/chunks\/([^/]+)$/);
    if (method === "GET" && chunk) {
      return chunk[1] === passage.chunk_id ? json(route, 200, passage) : json(route, 404, { detail: "Chunk not found" });
    }
    return route.fallback();
  });

  return mock;
}
