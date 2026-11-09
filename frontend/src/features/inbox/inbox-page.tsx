import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { listEscalations } from "@/api/escalations";
import { queryKeys } from "@/api/query-keys";
import { useSignedIn } from "@/auth/auth-context";
import { cn } from "@/lib/utils";
import { EscalationList } from "./escalation-list";
import { countByFilter, filterEscalations, filterFor, type InboxFilter } from "./inbox-logic";
import { ThreadView } from "./thread-view";

/**
 * Split inbox: the list of escalated conversations beside the open thread; stacked on phones, where the thread
 * replaces the list and a link goes back. The open thread is `?thread=<id>` so Back, reload and links work.
 * Live changes arrive through useEvents, which refetches these queries (escalation.changed, message.created,
 * conversation.updated).
 */
export function InboxPage() {
  const { user } = useSignedIn();
  const [params] = useSearchParams();
  const selectedId = params.get("thread");
  const [filter, setFilter] = useState<InboxFilter>("needs-reply");
  const [query, setQuery] = useState("");

  const escalations = useQuery({ queryKey: queryKeys.escalations, queryFn: listEscalations });
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
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-heading text-5xl sm:text-6xl">Inbox</h1>
        <p className="mt-3 max-w-prose text-muted-foreground">
          Customers the assistant has handed to a person. Open one to read it, answer, and resolve it when it is done.
        </p>
        <p className="sr-only" role="status" aria-live="polite">
          {announcement}
        </p>
      </header>

      <div className="grid gap-6 lg:h-[calc(100dvh-15rem)] lg:min-h-[36rem] lg:grid-cols-[minmax(18rem,24rem)_minmax(0,1fr)]">
        <section
          aria-label="Conversation list"
          className={cn("glass-1 min-h-0 flex-col overflow-hidden rounded-3xl", selectedId ? "hidden lg:flex" : "flex")}
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

        <section
          aria-label="Conversation"
          className={cn("glass-1 min-h-0 flex-col overflow-hidden rounded-3xl", selectedId ? "flex" : "hidden lg:flex")}
        >
          {selectedId ? (
            <ThreadView key={selectedId} conversationId={selectedId} role={user.role} />
          ) : (
            <div className="p-6 sm:p-8">
              <p className="font-medium">Choose a conversation to read it.</p>
              <p className="mt-2 max-w-prose text-sm text-muted-foreground">
                The thread opens here. You can reply and then resolve it, which hands the customer back to the assistant.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
