import type { ChatStreamEvent } from "./stream";
import type { Citation, PendingInterrupt, ToolActivity } from "./types";

/**
 * The state of the turn the person just started, as a pure reducer. The server remains the source of truth for
 * saved messages (TanStack Query); this only holds what is not saved yet or not saved in a displayable form: the
 * answer while it streams, the action waiting for approval and the outcome of the decision.
 */
export type TurnPhase = "idle" | "streaming" | "interrupted" | "deciding" | "settled";

export interface TurnError {
  kind: "stream" | "network" | "decision";
  message: string;
}

export interface DecisionOutcome {
  approved: boolean;
  tool: string;
  arguments: unknown;
}

export interface TurnState {
  phase: TurnPhase;
  conversationId: string | null;
  /** How many saved messages were shown when the turn started; the turn is displayed after them. */
  baseCount: number;
  question: string;
  answer: string;
  citations: Citation[];
  tools: ToolActivity[];
  interrupt: PendingInterrupt | null;
  outcome: DecisionOutcome | null;
  /** Set when the turn ended in a handoff to a person. */
  escalation: { ticketId: string | null } | null;
  /** The conversation was already with an agent when this message was sent. */
  wasEscalated: boolean;
  doneStatus: string | null;
  stopped: boolean;
  error: TurnError | null;
}

/** Notes that stay in the thread after the turn is replaced by the saved messages. */
export type ThreadNote =
  | { id: string; anchor: number; kind: "decision"; outcome: DecisionOutcome }
  | { id: string; anchor: number; kind: "handoff"; ticketId: string | null };

export interface ChatState {
  turn: TurnState;
  notes: ThreadNote[];
}

export const idleTurn: TurnState = {
  phase: "idle",
  conversationId: null,
  baseCount: 0,
  question: "",
  answer: "",
  citations: [],
  tools: [],
  interrupt: null,
  outcome: null,
  escalation: null,
  wasEscalated: false,
  doneStatus: null,
  stopped: false,
  error: null,
};

export const initialChatState: ChatState = { turn: idleTurn, notes: [] };

export type ChatAction =
  | { type: "started"; conversationId: string; question: string; baseCount: number; wasEscalated: boolean }
  | { type: "stream"; event: ChatStreamEvent }
  | { type: "stopped" }
  | { type: "failed"; kind: "stream" | "network"; message: string }
  | { type: "decision_started" }
  | { type: "decision_resolved"; approved: boolean; answer: string | null; interrupt: PendingInterrupt | null }
  | { type: "decision_failed"; message: string }
  | { type: "cleared" }
  /** Another conversation was opened (or a new one started): nothing of the old one carries over. */
  | { type: "switched" };

function withTool(tools: ToolActivity[], tool: string, status: ToolActivity["status"]): ToolActivity[] {
  if (status === "started") return [...tools, { tool, status }];
  const index = tools.findIndex((entry) => entry.tool === tool && entry.status === "started");
  if (index === -1) return [...tools, { tool, status }];
  return tools.map((entry, i) => (i === index ? { tool, status } : entry));
}

function reduceStream(turn: TurnState, event: ChatStreamEvent): TurnState {
  if (turn.phase !== "streaming") return turn;
  switch (event.type) {
    case "token":
      return { ...turn, answer: turn.answer + event.text };
    case "reset":
      // The graph is regenerating: drop what was shown and start again from the next token.
      return { ...turn, answer: "" };
    case "citation":
      return turn.citations.some((c) => c.chunkId === event.citation.chunkId)
        ? turn
        : { ...turn, citations: [...turn.citations, event.citation] };
    case "tool_call":
      return { ...turn, tools: withTool(turn.tools, event.tool, event.status) };
    case "interrupt":
      return { ...turn, interrupt: event.interrupt };
    case "escalated":
      return { ...turn, escalation: { ticketId: event.ticketId } };
    case "done":
      return {
        ...turn,
        doneStatus: event.status,
        phase: turn.interrupt && event.status === "interrupted" ? "interrupted" : "settled",
      };
    case "error":
      return { ...turn, phase: "settled", error: { kind: "stream", message: event.message } };
  }
}

/** Where in the saved list the notes of a finished turn belong. */
function noteAnchors(turn: TurnState): { decision: number; handoff: number } {
  return { decision: turn.baseCount + 1, handoff: turn.baseCount + 1 + (turn.answer.trim() === "" ? 0 : 1) };
}

/** Adds the handoff note the moment a turn that started with the assistant ends with a person taking over. */
function withHandoffNote(state: ChatState, next: TurnState): ChatState {
  const justSettled = state.turn.phase !== "settled" && next.phase === "settled";
  if (!justSettled || !next.escalation || next.wasEscalated) return { ...state, turn: next };
  const note: ThreadNote = {
    id: `handoff-${next.baseCount}`,
    anchor: noteAnchors(next).handoff,
    kind: "handoff",
    ticketId: next.escalation.ticketId,
  };
  return { turn: next, notes: [...state.notes.filter((n) => n.id !== note.id), note] };
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  const { turn } = state;
  switch (action.type) {
    case "started":
      return {
        ...state,
        turn: {
          ...idleTurn,
          phase: "streaming",
          conversationId: action.conversationId,
          baseCount: action.baseCount,
          question: action.question,
          wasEscalated: action.wasEscalated,
        },
      };
    case "stream":
      return withHandoffNote(state, reduceStream(turn, action.event));
    case "stopped":
      return turn.phase === "streaming" ? { ...state, turn: { ...turn, phase: "settled", stopped: true } } : state;
    case "failed":
      return turn.phase === "streaming"
        ? { ...state, turn: { ...turn, phase: "settled", error: { kind: action.kind, message: action.message } } }
        : state;
    case "decision_started":
      return turn.phase === "interrupted" ? { ...state, turn: { ...turn, phase: "deciding", error: null } } : state;
    case "decision_resolved": {
      if (turn.phase !== "deciding" || !turn.interrupt) return state;
      const outcome: DecisionOutcome = {
        approved: action.approved,
        tool: turn.interrupt.tool,
        arguments: turn.interrupt.arguments,
      };
      const answer = action.answer !== null && action.answer.trim() !== "" ? action.answer : "";
      const note: ThreadNote = {
        id: `decision-${turn.interrupt.interruptId}`,
        anchor: noteAnchors(turn).decision,
        kind: "decision",
        outcome,
      };
      const notes = [...state.notes, note];
      if (action.interrupt) {
        // The resumed turn paused again on another action.
        return { turn: { ...turn, outcome, answer, citations: [], phase: "interrupted", interrupt: action.interrupt }, notes };
      }
      return { turn: { ...turn, outcome, answer, citations: [], phase: "settled", interrupt: null }, notes };
    }
    case "decision_failed":
      return turn.phase === "deciding"
        ? { ...state, turn: { ...turn, phase: "interrupted", error: { kind: "decision", message: action.message } } }
        : state;
    case "cleared":
      return { ...state, turn: idleTurn };
    case "switched":
      return initialChatState;
  }
}

/**
 * How many saved messages must exist before the saved conversation shows everything this turn showed, so the
 * live view can give way to it. `Infinity` for a failed turn, which stays visible (with its error) until the
 * person acts.
 */
export function savedMessagesExpected(turn: TurnState): number {
  if (turn.error) return Number.POSITIVE_INFINITY;
  // A stopped turn is still finished by the server, which saves the whole answer.
  const answered = turn.stopped || turn.answer.trim() !== "";
  return turn.baseCount + 1 + (answered ? 1 : 0);
}

/** True once the saved messages have caught up with a settled turn, so it can be dropped without a visible change. */
export function isSuperseded(turn: TurnState, savedCount: number): boolean {
  return turn.phase === "settled" && savedCount >= savedMessagesExpected(turn);
}
