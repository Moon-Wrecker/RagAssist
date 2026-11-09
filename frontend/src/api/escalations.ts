import { apiJson, jsonBody } from "./http";
import type { components } from "./schema";

type Schemas = components["schemas"];

export type EscalationSummary = Schemas["EscalationSummary"];
export type EscalationList = Schemas["EscalationListResponse"];
export type ConversationDetail = Schemas["ConversationDetailResponse"];
export type ReplyResult = Schemas["EscalationReplyResponse"];
export type ResolveResult = Schemas["EscalationResolveResponse"];

/** The API caps a page at 100. */
export const ESCALATION_PAGE_SIZE = 100;

/** An escalation id is the id of the conversation it belongs to. */
export function listEscalations(): Promise<EscalationList> {
  return apiJson<EscalationList>(`/v1/escalations?limit=${ESCALATION_PAGE_SIZE}&offset=0`);
}

export function fetchConversation(conversationId: string): Promise<ConversationDetail> {
  return apiJson<ConversationDetail>(`/v1/conversations/${encodeURIComponent(conversationId)}`);
}

export function replyToEscalation(escalationId: string, text: string): Promise<ReplyResult> {
  return apiJson<ReplyResult>(`/v1/escalations/${encodeURIComponent(escalationId)}/reply`, {
    method: "POST",
    ...jsonBody({ text }),
  });
}

export function resolveEscalation(escalationId: string): Promise<ResolveResult> {
  return apiJson<ResolveResult>(`/v1/escalations/${encodeURIComponent(escalationId)}/resolve`, { method: "POST" });
}
