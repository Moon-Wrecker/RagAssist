import type { UseQueryResult } from "@tanstack/react-query";
import { useMemo, useState, type RefObject } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ConversationList } from "./api";
import { filterConversations } from "./filter-conversations";
import { GlassSheet } from "./glass-sheet";

function statusLabel(status: string): string | null {
  if (status === "escalated") return "With an agent";
  if (status === "resolved") return "Resolved";
  return null;
}

function when(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const sameDay = date.toDateString() === new Date().toDateString();
  return sameDay
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString([], { day: "numeric", month: "short" });
}

/** The glass slide-over with past conversations. Choosing one opens it and closes the sheet. */
export function HistorySheet({
  open,
  onOpenChange,
  history,
  activeId,
  onSelect,
  onNew,
  returnFocusTo,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  history: UseQueryResult<ConversationList>;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  returnFocusTo: RefObject<HTMLElement | null>;
}) {
  const [query, setQuery] = useState("");
  const items = useMemo(() => filterConversations(history.data?.items ?? [], query), [history.data, query]);
  const total = history.data?.total ?? 0;
  const loaded = history.data?.items.length ?? 0;

  return (
    <GlassSheet
      open={open}
      onOpenChange={onOpenChange}
      placement="left"
      title="History"
      description="Your past conversations. Choose one to open it."
      returnFocusTo={returnFocusTo}
    >
      <div className="space-y-4">
        <Button variant="outline" size="sm" onClick={onNew} className="w-full rounded-full">
          New conversation
        </Button>
        {loaded > 5 ? (
          <Input
            type="search"
            aria-label="Filter conversations by title"
            placeholder="Filter by title"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="rounded-full"
          />
        ) : null}
        {history.isPending ? (
          <p role="status" className="font-mono text-sm text-muted-foreground">
            Loading conversations
          </p>
        ) : history.isError ? (
          <div role="alert" className="space-y-2 text-sm">
            <p>Your conversations could not be loaded.</p>
            <Button variant="outline" size="sm" onClick={() => void history.refetch()}>
              Try again
            </Button>
          </div>
        ) : loaded === 0 ? (
          <p className="text-sm text-muted-foreground">No conversations yet. Send a message and it will be listed here.</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No loaded conversation has that in its title.</p>
        ) : (
          <ul className="-mx-3">
            {items.map((item) => {
              const label = statusLabel(item.status);
              const current = item.conversation_id === activeId;
              return (
                <li key={item.conversation_id}>
                  <button
                    type="button"
                    aria-current={current ? "true" : undefined}
                    onClick={() => onSelect(item.conversation_id)}
                    className={cn(
                      "block w-full rounded-2xl px-3 py-2 text-left hover:bg-accent",
                      current && "bg-accent",
                    )}
                  >
                    <span className={cn("block truncate text-sm", current && "font-medium")}>{item.title}</span>
                    <span className="mt-0.5 flex gap-2 font-mono text-xs text-muted-foreground">
                      <span>{when(item.updated_at)}</span>
                      {label ? <span className="rounded-full border px-2 leading-5">{label}</span> : null}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {total > loaded ? (
          <p className="font-mono text-xs text-muted-foreground">{`Showing the latest ${loaded} of ${total}.`}</p>
        ) : null}
      </div>
    </GlassSheet>
  );
}
