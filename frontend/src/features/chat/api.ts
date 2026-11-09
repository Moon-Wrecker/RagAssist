import { apiFetch, apiJson, jsonBody } from "@/api/http";
import { apiErrorFromResponse } from "@/api/errors";
import { parseMessages } from "./messages";
import type { ActionDecisionResult, ChatMessage, ConversationDetail, ConversationSummary, Passage, PendingInterrupt } from "./types";

export interface ConversationList {
  items: ConversationSummary[];
  total: number;
}

export interface Conversation {
  id: string;
  title: string;
  status: string;
  messages: ChatMessage[];
  updatedAt: string;
}

export const HISTORY_PAGE_SIZE = 50;

/** Passages never change once indexed, so they are cached by chunk id. */
export const passageKey = (chunkId: string) => ["chunks", chunkId] as const;

export function listConversations(): Promise<ConversationList> {
  return apiJson<ConversationList>(`/v1/conversations?limit=${HISTORY_PAGE_SIZE}`);
}

export function createConversation(title: string): Promise<ConversationSummary> {
  return apiJson<ConversationSummary>("/v1/conversations", { method: "POST", ...jsonBody({ title }) });
}

export async function getConversation(id: string): Promise<Conversation> {
  const detail = await apiJson<ConversationDetail>(`/v1/conversations/${encodeURIComponent(id)}`);
  return {
    id: detail.conversation_id,
    title: detail.title,
    status: detail.status,
    messages: parseMessages(detail.messages ?? []),
    updatedAt: detail.updated_at,
  };
}

export function getPassage(chunkId: string): Promise<Passage> {
  return apiJson<Passage>(`/v1/chunks/${encodeURIComponent(chunkId)}`);
}

/**
 * Sends a message and returns the open event stream. The caller reads it with `readChatStream` and aborts
 * `signal` to stop watching (the server still finishes and saves the turn).
 */
export async function sendMessage(conversationId: string, content: string, signal: AbortSignal): Promise<ReadableStream<Uint8Array<ArrayBuffer>>> {
  const response = await apiFetch(`/v1/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    signal,
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify({ content, stream: true }),
  });
  if (!response.ok) throw await apiErrorFromResponse(response);
  if (!response.body) throw new Error("The server answered without a stream.");
  return response.body;
}

export interface DecisionResult {
  answer: string | null;
  interrupt: PendingInterrupt | null;
}

/** The approve or deny call. What runs is what the server stored with the interrupt, never this request. */
export async function decideAction(conversationId: string, interruptId: string, approved: boolean): Promise<DecisionResult> {
  const result = await apiJson<ActionDecisionResult>(
    `/v1/conversations/${encodeURIComponent(conversationId)}/actions/${encodeURIComponent(interruptId)}`,
    { method: "POST", ...jsonBody({ approved }) },
  );
  const next = result.interrupt;
  const nextId = next && typeof next.interrupt_id === "string" ? next.interrupt_id : "";
  return {
    answer: result.answer ?? null,
    interrupt:
      next && nextId !== "" && typeof next.tool === "string"
        ? {
            interruptId: nextId,
            tool: next.tool,
            arguments: next.arguments ?? {},
            callId: typeof next.call_id === "string" ? next.call_id : null,
          }
        : null,
  };
}
