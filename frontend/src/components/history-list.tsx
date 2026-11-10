import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useMemo, useState } from "react";
import { queryKeys } from "@/api/query-keys";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { listConversations } from "@/features/chat/api";
import { filterConversations } from "@/features/chat/filter-conversations";
import { spring, staggerStep } from "@/lib/motion";
import { cn } from "@/lib/utils";

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

/**
 * Past conversations for the sidebar and the phone sheet. Rows are plain (no glass): the list sits inside a glass
 * surface already. It staggers in once on first load and never on a refetch. The API pages history at 50 rows, so
 * the DOM stays small; `content-visibility: auto` skips painting rows that are scrolled out of view.
 */
export function HistoryList({
  activeId,
  onSelect,
  onNew,
}: {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const queryClient = useQueryClient();
  const history = useQuery({ queryKey: queryKeys.conversations, queryFn: listConversations });
  const [query, setQuery] = useState("");
  const items = useMemo(() => filterConversations(history.data?.items ?? [], query), [history.data, query]);
  const loaded = history.data?.items.length ?? 0;
  const total = history.data?.total ?? 0;
  // Stagger the rows in once: only when this list mounts before any history has been loaded (never on a refetch,
  // and not when the sidebar remounts with the data already cached).
  const [stagger] = useState(() => queryClient.getQueryData(queryKeys.conversations) === undefined);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <Button variant="secondary" size="sm" onClick={onNew} className="w-full">
        New conversation
      </Button>
      {loaded > 5 ? (
        <Input
          type="search"
          aria-label="Filter conversations by title"
          placeholder="Filter by title"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="h-8"
        />
      ) : null}
      <div className="scroll-area -mx-1 min-h-0 flex-1 px-1">
        {history.isPending ? (
          <p role="status" className="text-meta px-2 py-2 text-muted-foreground">
            Loading
          </p>
        ) : history.isError ? (
          <div role="alert" className="space-y-2 px-2 py-2 text-sm">
            <p>Your conversations could not be loaded.</p>
            <Button variant="secondary" size="sm" onClick={() => void history.refetch()}>
              Try again
            </Button>
          </div>
        ) : loaded === 0 ? (
          <p className="px-2 py-2 text-sm text-muted-foreground">Nothing here yet.</p>
        ) : items.length === 0 ? (
          <p className="px-2 py-2 text-sm text-muted-foreground">No title matches.</p>
        ) : (
          <ul aria-label="Conversations">
            {items.map((item, index) => {
              const label = statusLabel(item.status);
              const current = item.conversation_id === activeId;
              return (
                <motion.li
                  key={item.conversation_id}
                  initial={stagger ? { opacity: 0, y: 6 } : false}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ ...spring.snappy, delay: stagger ? Math.min(index, 10) * staggerStep : 0 }}
                  className="[contain-intrinsic-size:auto_2.75rem] [content-visibility:auto]"
                >
                  <button
                    type="button"
                    aria-current={current ? "true" : undefined}
                    onClick={() => onSelect(item.conversation_id)}
                    className={cn("block w-full rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-accent", current && "bg-accent")}
                  >
                    <span className="block truncate text-sm">{item.title}</span>
                    <span className="text-meta mt-0.5 flex gap-2 text-muted-foreground">
                      <span>{when(item.updated_at)}</span>
                      {label ? <span>{label}</span> : null}
                    </span>
                  </button>
                </motion.li>
              );
            })}
          </ul>
        )}
        {total > loaded ? <p className="text-meta px-2 py-2 text-muted-foreground">{`Latest ${loaded} of ${total}`}</p> : null}
      </div>
    </div>
  );
}
