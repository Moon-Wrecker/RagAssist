import type { components } from "@/api/schema";

type Schemas = components["schemas"];

export type ConversationSummary = Schemas["ConversationResponse"];
export type ConversationDetail = Schemas["ConversationDetailResponse"];
export type Passage = Schemas["ChunkResponse"];
export type ActionDecisionResult = Schemas["ActionDecisionResponse"];

/** The status a conversation can have on the server (`open`, `escalated`, `resolved`); unknown values are kept. */
export type ConversationStatus = string;

/** A source behind an answer. `[n]` in the text refers to the n-th citation of the message. */
export interface Citation {
  chunkId: string;
  documentId: string;
  title: string;
  page: number | null;
  headingPath: string[];
}

/** A saved message as the thread shows it. Agent replies come from a human, so they are marked as such. */
export interface ChatMessage {
  /** Stable within one conversation fetch: the position in the server list. */
  id: string;
  role: "user" | "assistant" | "agent";
  text: string;
  citations: Citation[];
  createdAt: string | null;
}

/** A write action the assistant wants to run, paused until the person decides. Values are shown exactly. */
export interface PendingInterrupt {
  interruptId: string;
  tool: string;
  arguments: unknown;
  callId: string | null;
}

export interface ToolActivity {
  tool: string;
  status: "started" | "completed";
}
