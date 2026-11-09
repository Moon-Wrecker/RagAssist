import type { ChatMessage, Citation } from "./types";

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** A citation from a stream frame or a saved message. Needs a chunk id; everything else is optional. */
export function parseCitation(value: unknown): Citation | null {
  const raw = asRecord(value);
  const chunkId = raw ? asString(raw.chunk_id) : "";
  if (!raw || chunkId === "") return null;
  const page = typeof raw.page === "number" && Number.isFinite(raw.page) ? raw.page : null;
  const heading = Array.isArray(raw.heading_path) ? raw.heading_path.filter((part): part is string => typeof part === "string") : [];
  return { chunkId, documentId: asString(raw.document_id), title: asString(raw.title), page, headingPath: heading };
}

/** The saved messages of a conversation, dropping anything that is not a user, assistant or agent turn with text. */
export function parseMessages(raw: readonly Record<string, unknown>[]): ChatMessage[] {
  const messages: ChatMessage[] = [];
  raw.forEach((entry, index) => {
    const role = entry.role;
    if (role !== "user" && role !== "assistant" && role !== "agent") return;
    const text = asString(entry.text);
    if (text === "") return;
    const citations = Array.isArray(entry.citations)
      ? entry.citations.map(parseCitation).filter((c): c is Citation => c !== null)
      : [];
    messages.push({
      id: `m${index}`,
      role,
      text,
      citations,
      createdAt: typeof entry.created_at === "string" ? entry.created_at : null,
    });
  });
  return messages;
}
