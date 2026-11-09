import { CircleCheck, CircleDot, Search } from "lucide-react";
import { Link } from "react-router";
import type { EscalationSummary } from "@/api/escalations";
import { StatusMark } from "@/components/status-mark";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { FILTER_LABELS, isOpen, type InboxFilter } from "./inbox-logic";

const FILTERS: InboxFilter[] = ["needs-reply", "resolved", "all"];

export function ListStatus({ item }: { item: Pick<EscalationSummary, "status"> }) {
  return isOpen(item) ? (
    <StatusMark icon={CircleDot} label="Needs a reply" emphasis="strong" />
  ) : (
    <StatusMark icon={CircleCheck} label="Resolved" emphasis="muted" />
  );
}

/** Filter buttons with counts, a search box and the list of conversations. Selection lives in the URL. */
export function EscalationList({
  items,
  total,
  counts,
  filter,
  onFilter,
  query,
  onQuery,
  selectedId,
  state,
  onRetry,
}: {
  items: EscalationSummary[];
  total: number;
  counts: Record<InboxFilter, number>;
  filter: InboxFilter;
  onFilter: (filter: InboxFilter) => void;
  query: string;
  onQuery: (query: string) => void;
  selectedId: string | null;
  state: "loading" | "error" | "ready";
  onRetry: () => void;
}) {
  const loadedCount = counts.all;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-3 border-b p-5">
        <div role="group" aria-label="Show conversations" className="flex flex-wrap gap-1.5">
          {FILTERS.map((value) => (
            <Button
              key={value}
              type="button"
              size="sm"
              variant={filter === value ? "default" : "outline"}
              aria-pressed={filter === value}
              onClick={() => onFilter(value)}
            >
              {FILTER_LABELS[value]}
              <span className="font-mono text-xs opacity-80">{counts[value]}</span>
            </Button>
          ))}
        </div>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            aria-label="Search conversations"
            placeholder="Search by topic"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {state === "loading" ? (
          <p className="p-4 text-sm text-muted-foreground" role="status">
            Loading conversations
          </p>
        ) : state === "error" ? (
          <div className="flex flex-col items-start gap-3 p-4" role="alert">
            <p className="text-sm">The conversations could not be loaded.</p>
            <Button variant="outline" size="sm" onClick={onRetry}>
              Try again
            </Button>
          </div>
        ) : items.length === 0 ? (
          <EmptyList filter={filter} query={query} loadedCount={loadedCount} onClear={() => onQuery("")} onShowResolved={() => onFilter("resolved")} />
        ) : (
          <ul aria-label="Conversations" className="flex flex-col gap-1 p-2.5">
            {items.map((item) => {
              const selected = item.escalation_id === selectedId;
              return (
                <li key={item.escalation_id}>
                  <Link
                    to={{ search: `?thread=${encodeURIComponent(item.escalation_id)}` }}
                    aria-current={selected ? "true" : undefined}
                    className={cn(
                      "block rounded-2xl px-4 py-3.5 ring-1 ring-transparent transition-colors hover:bg-accent focus-visible:-outline-offset-2",
                      selected && "bg-accent ring-border-strong",
                    )}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <ListStatus item={item} />
                      <span className="font-mono text-xs text-muted-foreground">{timeAgo(item.updated_at)}</span>
                    </span>
                    <span className={cn("mt-1.5 line-clamp-2 block text-sm", isOpen(item) ? "font-medium" : "text-muted-foreground")}>
                      {item.summary || "Conversation without a summary"}
                    </span>
                    <span className="mt-1 block font-mono text-xs text-muted-foreground">Priority {item.priority}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        {state === "ready" && total > loadedCount ? (
          <p className="border-t p-4 font-mono text-xs text-muted-foreground">
            Showing the {loadedCount} most recently updated of {total}.
          </p>
        ) : null}
      </div>
    </div>
  );
}

function EmptyList({
  filter,
  query,
  loadedCount,
  onClear,
  onShowResolved,
}: {
  filter: InboxFilter;
  query: string;
  loadedCount: number;
  onClear: () => void;
  onShowResolved: () => void;
}) {
  if (query.trim() !== "") {
    return (
      <div className="flex flex-col items-start gap-3 p-4">
        <p className="text-sm">No conversation matches that search.</p>
        <Button variant="outline" size="sm" onClick={onClear}>
          Clear the search
        </Button>
      </div>
    );
  }
  if (filter === "needs-reply") {
    return (
      <div className="flex flex-col items-start gap-3 p-4">
        <p className="text-sm font-medium">Nothing is waiting for a reply.</p>
        <p className="text-sm text-muted-foreground">
          When the assistant hands a customer to a person, the conversation appears here without a refresh.
        </p>
        {loadedCount > 0 ? (
          <Button variant="outline" size="sm" onClick={onShowResolved}>
            Show resolved conversations
          </Button>
        ) : null}
      </div>
    );
  }
  return (
    <div className="p-4">
      <p className="text-sm">No conversations here yet.</p>
    </div>
  );
}
