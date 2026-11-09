import { describe, expect, it } from "vitest";
import { queryKeys } from "@/api/query-keys";
import { invalidationsFor } from "./invalidation";

describe("invalidationsFor", () => {
  it("refetches everything on resync", () => {
    expect(invalidationsFor({ type: "resync", data: {} })).toBe("all");
  });

  it("refetches the document list and the job on job.updated", () => {
    expect(invalidationsFor({ type: "job.updated", data: { job_id: "j1", document_id: "d1" } })).toEqual([
      queryKeys.documents,
      queryKeys.ingestionJob("j1"),
    ]);
  });

  it("refetches documents on document.changed", () => {
    expect(invalidationsFor({ type: "document.changed", data: { document_id: "d1" } })).toEqual([queryKeys.documents]);
  });

  it("refetches the conversation, the list and the inbox on message.created", () => {
    expect(invalidationsFor({ type: "message.created", data: { conversation_id: "c1" } })).toEqual([
      queryKeys.conversation("c1"),
      queryKeys.conversations,
      queryKeys.escalations,
    ]);
  });

  it("does the same for conversation.updated", () => {
    expect(invalidationsFor({ type: "conversation.updated", data: { conversation_id: "c1" } })).toContainEqual(
      queryKeys.conversation("c1"),
    );
  });

  it("refetches the inbox and the conversation on escalation.changed", () => {
    expect(
      invalidationsFor({ type: "escalation.changed", data: { conversation_id: "c1", ticket_id: "TICK-1" } }),
    ).toEqual([queryKeys.escalations, queryKeys.conversation("c1")]);
  });

  it("still refetches the lists when the id is missing", () => {
    expect(invalidationsFor({ type: "message.created", data: {} })).toEqual([
      queryKeys.conversations,
      queryKeys.escalations,
    ]);
  });

  it("ignores control events and event types it does not know", () => {
    expect(invalidationsFor({ type: "ready", data: {} })).toEqual([]);
    expect(invalidationsFor({ type: "reauth", data: {} })).toEqual([]);
    expect(invalidationsFor({ type: "something.new", data: { conversation_id: "c1" } })).toEqual([]);
  });
});
