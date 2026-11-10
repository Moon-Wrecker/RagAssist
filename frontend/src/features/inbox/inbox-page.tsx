import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { listEscalations } from "@/api/escalations";
import { queryKeys } from "@/api/query-keys";
import { useSignedIn } from "@/auth/auth-context";
import { PageFrame } from "@/components/page-frame";
import { cn } from "@/lib/utils";
import { EscalationList } from "./escalation-list";
import { countByFilter, filterEscalations, filterFor, type InboxFilter } from "./inbox-logic";
import { ThreadView } from "./thread-view";

const RECOVERY_POLL_MS = 8_000;

/**
 * Split inbox on one regular glass surface: the list of escalated conversations, one hairline, the open thread. On
 * phones the thread replaces the list and a link goes back. The open thread is `?thread=<id>` so Back, reload and
 * links work. Live changes arrive through useEvents, which refetches these queries (escalation.changed,
 * message.created, conversation.updated).
 */
export function InboxPage() {
  const { user } = useSignedIn();
  const [params] = useSearchParams();
  const selectedId = params.get("thread");
  const [filter, setFilter] = useState<InboxFilter>("needs-reply");
  const [query, setQuery] = useState("");

  // A failed load heals itself: ask again every few seconds until it works (a restart of the API is the usual cause).
  const escalations = useQuery({
    queryKey: queryKeys.escalations,
    queryFn: listEscalations,
    refetchInterval: (query) => (query.state.status === "error" ? RECOVERY_POLL_MS : false),
  });
  const all = useMemo(() => escalations.data?.items ?? [], [escalations.data]);
  const counts = useMemo(() => countByFilter(all), [all]);
  const visible = useMemo(() => filterEscalations(all, filter, query), [all, filter, query]);

  // A link to a resolved conversation should open the list that contains it, once, when the data first arrives.
  const alignedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedId || alignedFor.current === selectedId || all.length === 0) return;
    alignedFor.current = selectedId;
    setFilter(filterFor(all.find((item) => item.escalation_id === selectedId)));
  }, [selectedId, all]);

  const waiting = counts["needs-reply"];
  const announcement =
    escalations.isSuccess ? (waiting === 0 ? "No conversations need a reply." : `${waiting} ${waiting === 1 ? "conversation needs" : "conversations need"} a reply.`) : "";

  return (
    <PageFrame title="Inbox" mode="fill">
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>
      <div className="h-full min-h-0 px-(--gutter)">
        <div className="glass-regular grid h-full min-h-0 overflow-hidden rounded-(--r-surface) lg:grid-cols-[minmax(18rem,24rem)_minmax(0,1fr)]">
          <section
            aria-label="Conversation list"
            className={cn("min-h-0 flex-col lg:border-r lg:border-border", selectedId ? "hidden lg:flex" : "flex")}
          >
            <EscalationList
              items={visible}
              total={escalations.data?.total ?? 0}
              counts={counts}
              filter={filter}
              onFilter={setFilter}
              query={query}
              onQuery={setQuery}
              selectedId={selectedId}
              state={escalations.isPending ? "loading" : escalations.isError ? "error" : "ready"}
              onRetry={() => void escalations.refetch()}
            />
          </section>

          <section aria-label="Conversation" className={cn("relative min-h-0 min-w-0 flex-col", selectedId ? "flex" : "hidden lg:flex")}>
            {selectedId ? (
              <ThreadView key={selectedId} conversationId={selectedId} role={user.role} />
            ) : (
              <p className="m-auto px-6 text-center text-sm text-muted-foreground">Choose a conversation.</p>
            )}
          </section>
        </div>
      </div>
    </PageFrame>
  );
}
