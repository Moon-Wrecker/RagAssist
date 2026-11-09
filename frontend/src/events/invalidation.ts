import type { QueryKey } from "@tanstack/react-query";
import { queryKeys } from "@/api/query-keys";

/**
 * Events from `GET /v1/events` (docs/api/sse-contract.md). They carry only a type and ids; the client refetches
 * through the normal API, which enforces tenant, owner and role again.
 */
export type LiveEventType =
  | "ready"
  | "job.updated"
  | "document.changed"
  | "message.created"
  | "conversation.updated"
  | "escalation.changed"
  | "resync"
  | "reauth";

export interface LiveEvent {
  type: string;
  data: Record<string, unknown>;
}

function idOf(data: Record<string, unknown>, field: string): string | null {
  const value = data[field];
  return typeof value === "string" && value !== "" ? value : null;
}

/**
 * Which queries an event makes stale. `"all"` means everything (resync, or a reconnect after missed events).
 * Control events (`ready`, `reauth`) and unknown types invalidate nothing: a newer server may add event types and
 * an older client must ignore them.
 */
export function invalidationsFor(event: LiveEvent): QueryKey[] | "all" {
  const conversationId = idOf(event.data, "conversation_id");
  switch (event.type) {
    case "resync":
      return "all";
    case "job.updated": {
      const jobId = idOf(event.data, "job_id");
      return [queryKeys.documents, ...(jobId ? [queryKeys.ingestionJob(jobId)] : [])];
    }
    case "document.changed":
      return [queryKeys.documents];
    case "message.created":
    case "conversation.updated":
      return [
        ...(conversationId ? [queryKeys.conversation(conversationId)] : []),
        queryKeys.conversations,
        queryKeys.escalations,
      ];
    case "escalation.changed":
      return [queryKeys.escalations, ...(conversationId ? [queryKeys.conversation(conversationId)] : [])];
    default:
      return [];
  }
}
