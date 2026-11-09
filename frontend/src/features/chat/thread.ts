import type { ChatMessage } from "./types";
import { isSuperseded, type ThreadNote, type TurnState } from "./turn";

export type ThreadItem =
  | { kind: "message"; key: string; message: ChatMessage }
  | { kind: "note"; key: string; note: ThreadNote }
  | { kind: "live"; key: string; turn: TurnState };

/** Whether the live turn is still what the thread shows for it, or the saved messages have taken over. */
export function showsLiveTurn(turn: TurnState, savedCount: number): boolean {
  return turn.phase !== "idle" && !isSuperseded(turn, savedCount);
}

/**
 * The thread in reading order: saved messages with notes (decision outcomes, handoff moments) in place, then the
 * live turn if it has not been replaced by its saved version yet. While a turn is live the messages after its
 * `baseCount` are hidden, because the live turn already shows them (and a refetch during the stream must not
 * show the question twice).
 */
export function buildThread(messages: readonly ChatMessage[], notes: readonly ThreadNote[], turn: TurnState): ThreadItem[] {
  const live = showsLiveTurn(turn, messages.length);
  const shown = live ? messages.slice(0, turn.baseCount) : messages;
  const items: ThreadItem[] = [];
  const noteItem = (note: ThreadNote): ThreadItem => ({ kind: "note", key: note.id, note });
  const eligible = live ? notes.filter((note) => note.anchor <= shown.length) : notes;

  shown.forEach((message, index) => {
    for (const note of eligible) if (note.anchor === index) items.push(noteItem(note));
    items.push({ kind: "message", key: message.id, message });
  });
  for (const note of eligible) if (note.anchor >= shown.length) items.push(noteItem(note));
  if (live) items.push({ kind: "live", key: "live", turn });
  return items;
}
