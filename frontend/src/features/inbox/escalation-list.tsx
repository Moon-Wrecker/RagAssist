import { CircleCheck, CircleDot, Search } from "lucide-react";
import { Link } from "react-router";
import type { EscalationSummary } from "@/api/escalations";
import { EmptyState, ErrorState } from "@/components/empty-state";
import { Segmented } from "@/components/segmented";
import { ListSkeleton } from "@/components/skeleton";
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

/**
 * The left column of the inbox: a sticky glass toolbar (segmented filter with counts, search) over dense rows.
 * Rows are plain with hairline dividers; only the hovered or open row gets thin glass. Selection lives in the URL.
 */
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
    <div className="scroll-area min-h-0 flex-1">
      <div className="sticky-glass sticky top-0 z-10 flex flex-col gap-3 border-b border-border p-4">
        {/* Counts appear only once the list is loaded, so a failed load never reads as "0". */}
        <Segmented
          label="Show conversations"
          value={filter}
          onChange={onFilter}
          options={FILTERS.map((value) => ({ value, label: FILTER_LABELS[value], count: state === "ready" ? counts[value] : undefined }))}
        />
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            aria-label="Search conversations"
            placeholder="Search by topic"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            className="h-9 rounded-full pl-10"
          />
        </div>
      </div>

      {state === "loading" ? (
        <ListSkeleton label="Loading conversations" />
      ) : state === "error" ? (
        <ErrorState what="The conversations" onRetry={onRetry} />
      ) : items.length === 0 ? (
        <EmptyList filter={filter} query={query} loadedCount={loadedCount} onClear={() => onQuery("")} onShowResolved={() => onFilter("resolved")} />
      ) : (
        <ul aria-label="Conversations">
          {items.map((item) => {
            const selected = item.escalation_id === selectedId;
            return (
              <li key={item.escalation_id} className="border-t border-border first:border-t-0">
                <Link
                  to={{ search: `?thread=${encodeURIComponent(item.escalation_id)}` }}
                  aria-current={selected ? "true" : undefined}
                  className={cn("row-hover block px-5 py-3 focus-visible:-outline-offset-2", selected && "row-selected")}
                >
                  <span className="flex items-baseline justify-between gap-3">
                    <span className={cn("line-clamp-1 text-sm", isOpen(item) ? "font-medium" : "text-muted-foreground")}>
                      {item.summary || "Conversation without a summary"}
                    </span>
                    <span className="text-meta shrink-0 text-muted-foreground">{timeAgo(item.updated_at)}</span>
                  </span>
                  <span className="mt-1.5 flex items-center justify-between gap-3">
                    <ListStatus item={item} />
                    <span className="text-meta text-muted-foreground">Priority {item.priority}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {state === "ready" && total > loadedCount ? (
        <p className="text-meta border-t border-border p-4 text-muted-foreground">
          Showing the {loadedCount} most recently updated of {total}.
        </p>
      ) : null}
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
      <EmptyState title="No conversation matches that search.">
        <Button variant="secondary" size="sm" onClick={onClear}>
          Clear the search
        </Button>
      </EmptyState>
    );
  }
  if (filter === "needs-reply") {
    return (
      <EmptyState title="Nothing is waiting for a reply." hint="New handoffs appear here.">
        {loadedCount > 0 ? (
          <Button variant="secondary" size="sm" onClick={onShowResolved}>
            Show resolved
          </Button>
        ) : null}
      </EmptyState>
    );
  }
  return <EmptyState title="No conversations here yet." />;
}
