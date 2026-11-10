import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowUp } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { ApiError } from "@/api/errors";
import {
  fetchConversation,
  replyToEscalation,
  resolveEscalation,
  type ConversationDetail,
  type EscalationList,
} from "@/api/escalations";
import { optimisticTarget, useOptimisticMutation } from "@/api/optimistic";
import { queryKeys } from "@/api/query-keys";
import { ThreadSkeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupTextarea } from "@/components/ui/input-group";
import { actionError } from "@/lib/error-message";
import { formatDateTime } from "@/lib/format";
import { useSize } from "@/lib/use-size";
import { cn } from "@/lib/utils";
import { ListStatus } from "./escalation-list";
import {
  canSendReply,
  parseMessages,
  replyBlockedReason,
  ROLE_LABELS,
  withPendingReply,
  withResolved,
  withThreadResolved,
  type ThreadMessage,
} from "./inbox-logic";

function messageRule(role: ThreadMessage["role"]): string {
  // Who spoke is carried by the label and by the rule beside the text (weight and pattern), never by colour.
  switch (role) {
    case "agent":
      return "border-l-4 border-solid border-foreground";
    case "assistant":
      return "border-l-2 border-dashed border-border-strong";
    default:
      return "border-l-2 border-solid border-border-strong";
  }
}

function Message({ message }: { message: ThreadMessage }) {
  return (
    <li className={cn("py-1 pl-4", messageRule(message.role), message.pending && "opacity-70")}>
      <p className="flex flex-wrap items-baseline gap-x-3 font-mono text-xs text-muted-foreground">
        <span className={cn("text-foreground", message.role === "agent" && "font-medium")}>{ROLE_LABELS[message.role]}</span>
        {message.pending ? <span>Sending</span> : message.createdAt ? <time dateTime={message.createdAt}>{formatDateTime(message.createdAt)}</time> : null}
      </p>
      <p className="mt-1 break-words whitespace-pre-wrap">{message.text}</p>
    </li>
  );
}

export function ThreadView({ conversationId, role }: { conversationId: string; role: string }) {
  const detail = useQuery({
    queryKey: queryKeys.conversation(conversationId),
    queryFn: () => fetchConversation(conversationId),
  });
  const headingRef = useRef<HTMLHeadingElement>(null);
  const logRef = useRef<HTMLOListElement>(null);
  const errorId = useId();
  const [replyRef, reply_] = useSize<HTMLFormElement>();
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const messages = useMemo(() => parseMessages(detail.data?.messages), [detail.data?.messages]);
  const status = detail.data?.status ?? "";

  // The page keys this component by conversation, so each thread starts with a clean composer. On phones the list
  // is hidden once a thread is open, so keyboard and screen-reader focus follows the person to the thread.
  useEffect(() => {
    if (typeof window.matchMedia === "function" && !window.matchMedia("(min-width: 1024px)").matches) {
      headingRef.current?.focus();
    }
  }, [conversationId]);

  // The reply box grows with the text up to a limit.
  useLayoutEffect(() => {
    const element = draftRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`;
  }, [draft]);

  // Keep the newest message in view as replies and customer messages arrive.
  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [messages.length, conversationId]);

  const detailTarget = optimisticTarget<ConversationDetail, string>(queryKeys.conversation(conversationId), (cache, text) =>
    withPendingReply(cache, text),
  );
  const reply = useOptimisticMutation<string, unknown>({
    targets: [detailTarget],
    mutationFn: (text) => replyToEscalation(conversationId, text),
    invalidate: [queryKeys.escalations],
    onError: (caught, text) => {
      // Put the words back so nothing the agent wrote is lost, and say what happened.
      setDraft((current) => (current.trim() === "" ? text : current));
      setError(actionError(caught, "send that reply"));
    },
  });
  const resolve = useOptimisticMutation<void, unknown>({
    targets: [
      optimisticTarget<ConversationDetail, void>(queryKeys.conversation(conversationId), (cache) => withThreadResolved(cache)),
      optimisticTarget<EscalationList, void>(queryKeys.escalations, (cache) => withResolved(cache, conversationId)),
    ],
    mutationFn: () => resolveEscalation(conversationId),
    onError: (caught) => setError(actionError(caught, "resolve this conversation")),
  });

  const blocked = replyBlockedReason({ status, role });
  const sendable = canSendReply({ status, text: draft, role, sending: false });

  function send() {
    if (!sendable) return;
    const text = draft.trim();
    setDraft("");
    setError(null);
    reply.mutate(text);
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    send();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      send();
    }
  }

  if (detail.isPending) return <ThreadSkeleton label="Loading the conversation" />;
  if (detail.isError) {
    const gone = detail.error instanceof ApiError && detail.error.status === 404;
    return (
      <div role="alert" className="m-auto flex flex-col items-center gap-3 px-6 py-14 text-center">
        <p className="font-medium">{gone ? "This conversation is not available." : "The conversation could not be loaded."}</p>
        <div className="flex gap-2">
          {gone ? null : (
            <Button variant="secondary" size="sm" onClick={() => void detail.refetch()}>
              Try again
            </Button>
          )}
          <Button asChild variant="ghost" size="sm">
            <Link to={{ search: "" }}>Back to the list</Link>
          </Button>
        </div>
      </div>
    );
  }

  const open = status === "escalated";
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="sticky-glass z-10 flex shrink-0 flex-col gap-2 border-b border-border px-5 py-4 sm:px-6">
        <Link
          to={{ search: "" }}
          className="inline-flex w-fit items-center gap-1.5 rounded-full text-sm text-muted-foreground hover:text-foreground lg:hidden"
        >
          <ArrowLeft aria-hidden className="size-4" />
          All conversations
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex-1 basis-56">
            <h2 ref={headingRef} tabIndex={-1} className="font-heading text-2xl break-words outline-none">
              {detail.data.title || "Conversation"}
            </h2>
            <p className="mt-1.5">
              <ListStatus item={{ status }} />
            </p>
          </div>
          {open ? (
            <Button variant="secondary" size="sm" onClick={() => resolve.mutate()} disabled={resolve.isPending}>
              {resolve.isPending ? "Resolving" : "Resolve and hand back"}
            </Button>
          ) : null}
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        <ol
          ref={logRef}
          role="log"
          aria-live="polite"
          aria-label="Messages"
          tabIndex={0}
          className="scroll-area absolute inset-0 flex flex-col gap-5 px-5 pt-5 sm:px-6"
          style={{ paddingBottom: blocked ? 20 : reply_.height + 28 }}
        >
          {messages.length === 0 ? (
            <li className="text-sm text-muted-foreground">No messages yet.</li>
          ) : (
            messages.map((message) => <Message key={message.key} message={message} />)
          )}
        </ol>

        {blocked ? null : (
          <form
            ref={replyRef}
            onSubmit={onSubmit}
            aria-label="Write a reply"
            className="glass-regular absolute inset-x-4 bottom-4 z-10 rounded-(--r-outer) p-(--pad) sm:inset-x-6"
            style={{ ["--r-outer" as string]: "1.75rem", ["--pad" as string]: "0.5rem" }}
          >
            <InputGroup>
              {error ? (
                <p id={errorId} role="alert" className="px-3 pt-1.5 text-sm">
                  {error}
                </p>
              ) : null}
              <div className="flex items-end gap-2">
                <InputGroupTextarea
                  ref={draftRef}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={onKeyDown}
                  rows={1}
                  aria-label="Reply to the customer"
                  aria-describedby={error ? errorId : undefined}
                  placeholder="Write to the customer"
                  className="max-h-[200px] min-h-10 px-3 py-2"
                />
                <InputGroupAddon align="inline-end" className="pb-0.5">
                  <span className="text-meta hidden text-muted-foreground sm:inline">Ctrl + Enter</span>
                  <Button type="submit" size="icon" disabled={!sendable} aria-label="Send reply" title="Send reply">
                    <ArrowUp aria-hidden />
                  </Button>
                </InputGroupAddon>
              </div>
            </InputGroup>
          </form>
        )}
      </div>

      {blocked ? <p className="shrink-0 border-t border-border px-5 py-4 text-sm text-muted-foreground sm:px-6">{blocked}</p> : null}
    </div>
  );
}
