import type { ConversationSummary } from "./types";

/** Filters the loaded conversations by title. There is no search endpoint, so this only sees what is loaded. */
export function filterConversations(items: readonly ConversationSummary[], query: string): ConversationSummary[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") return [...items];
  return items.filter((item) => item.title.toLowerCase().includes(needle));
}
