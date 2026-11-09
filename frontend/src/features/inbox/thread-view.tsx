import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
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
import { FormMessage } from "@/features/auth/form-message";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { actionError } from "@/lib/error-message";
import { formatDateTime } from "@/lib/format";
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
  const draftId = useId();
  const errorId = useId();
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

  if (detail.isPending) {
    return (
      <p className="p-6 text-sm text-muted-foreground" role="status">
        Loading the conversation
      </p>
    );
  }
  if (detail.isError) {
    const gone = detail.error instanceof ApiError && detail.error.status === 404;
    return (
      <div className="flex flex-col items-start gap-3 p-6" role="alert">
        <p className="font-medium">{gone ? "This conversation is not available." : "The conversation could not be loaded."}</p>
        <p className="text-sm text-muted-foreground">
          {gone ? "It may have been removed, or it belongs to another workspace." : "Check your connection and try again."}
        </p>
        <div className="flex gap-2">
          {gone ? null : (
            <Button variant="outline" size="sm" onClick={() => void detail.refetch()}>
              Try again
            </Button>
          )}
          <Button asChild variant="outline" size="sm">
            <Link to={{ search: "" }}>Back to the list</Link>
          </Button>
        </div>
      </div>
    );
  }

  const open = status === "escalated";
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex flex-col gap-3 border-b p-5 sm:p-6">
        <Link
          to={{ search: "" }}
          className="inline-flex w-fit items-center gap-1.5 rounded-full text-sm text-muted-foreground hover:text-foreground lg:hidden"
        >
          <ArrowLeft aria-hidden className="size-4" />
          All conversations
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1 basis-64">
            <h2 ref={headingRef} tabIndex={-1} className="font-heading text-3xl break-words outline-none sm:text-4xl">
              {detail.data.title || "Conversation"}
            </h2>
            <p className="mt-2 flex items-center gap-3">
              <ListStatus item={{ status }} />
            </p>
          </div>
          {open ? (
            <Button variant="outline" size="sm" onClick={() => resolve.mutate()} disabled={resolve.isPending}>
              {resolve.isPending ? "Resolving" : "Resolve and hand back"}
            </Button>
          ) : null}
        </div>
        {open ? (
          <p className="text-[0.8125rem] text-muted-foreground">
            Resolving closes the handoff. The assistant answers the customer's next message.
          </p>
        ) : null}
      </header>

      <ol
        ref={logRef}
        role="log"
        aria-live="polite"
        aria-label="Messages"
        tabIndex={0}
        className="flex min-h-32 flex-1 flex-col gap-5 overflow-y-auto p-5 sm:p-6"
      >
        {messages.length === 0 ? (
          <li className="text-sm text-muted-foreground">There are no messages in this conversation yet.</li>
        ) : (
          messages.map((message) => <Message key={message.key} message={message} />)
        )}
      </ol>

      <form onSubmit={onSubmit} className="flex flex-col gap-3 border-t p-5 sm:p-6">
        <FormMessage id={errorId} message={error} />
        {blocked ? (
          <p className="text-sm text-muted-foreground">{blocked}</p>
        ) : (
          <>
            <Label htmlFor={draftId}>Reply to the customer</Label>
            <Textarea
              id={draftId}
              rows={3}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onKeyDown}
              aria-describedby={error ? errorId : undefined}
              placeholder="Write what the customer should read"
            />
            <div className="flex items-center justify-between gap-3">
              <p className="hidden font-mono text-xs text-muted-foreground sm:block">Ctrl or Cmd + Enter sends</p>
              <Button type="submit" disabled={!sendable} className="ml-auto">
                Send reply
              </Button>
            </div>
          </>
        )}
      </form>
    </div>
  );
}
