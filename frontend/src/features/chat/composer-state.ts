import type { TurnState } from "./turn";

/** A conversation is with a person while a ticket is open: the assistant is silent and messages go to the agent. */
export function isHandoff(status: string | undefined): boolean {
  return status === "escalated";
}

export interface ComposerState {
  /** Who receives what the person writes. */
  audience: "assistant" | "agent";
  /** A turn is running: show Stop. */
  canStop: boolean;
  /** Sending is not possible right now, and why. */
  lockedFor: "streaming" | "approval" | "deciding" | null;
  label: string;
  submitLabel: string;
}

/** What the composer may do, from the conversation status and the live turn. Pure, so it is tested without a DOM. */
export function composerState(status: string | undefined, turn: TurnState): ComposerState {
  const audience = isHandoff(status) ? "agent" : "assistant";
  const label = audience === "agent" ? "Message to the support agent" : "Message";
  const submitLabel = "Send";
  switch (turn.phase) {
    case "streaming":
      return { audience, canStop: true, lockedFor: "streaming", label, submitLabel };
    case "interrupted":
      return { audience, canStop: false, lockedFor: "approval", label, submitLabel };
    case "deciding":
      return { audience, canStop: false, lockedFor: "deciding", label, submitLabel };
    default:
      return { audience, canStop: false, lockedFor: null, label, submitLabel };
  }
}
