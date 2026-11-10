import { History, Headset, Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/api/errors";
import { Panel } from "@/components/panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CitationPanel, type OpenSource } from "./citation-panel";
import { Composer } from "./composer";
import { HistorySheet } from "./history-sheet";
import type { OpenCitation } from "./markdown";
import { ThreadView } from "./thread-view";
import { useChat } from "./use-chat";

/** Scrolls to the end when the thread grows, but only if the person is already reading the end. */
function useFollowEnd(signal: unknown, resetKey: string | null) {
  const endRef = useRef<HTMLDivElement>(null);
  const following = useRef(true);

  useEffect(() => {
    const onScroll = () => {
      following.current = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 160;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    following.current = true;
  }, [resetKey]);

  useEffect(() => {
    if (following.current) endRef.current?.scrollIntoView({ block: "end" });
  }, [signal, resetKey]);

  return endRef;
}

function statusLine(status: string | undefined, messageCount: number): string {
  const parts: string[] = [];
  if (status === "escalated") parts.push("With a support agent");
  else if (status === "resolved") parts.push("Resolved");
  if (messageCount > 0) parts.push(`${messageCount} ${messageCount === 1 ? "message" : "messages"}`);
  return parts.join("  ·  ");
}

export function ChatPage() {
  const chat = useChat();
  const [opened, setOpened] = useState<(OpenSource & { conversationId: string | null }) | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const sourceTrigger = useRef<HTMLElement | null>(null);
  const historyTrigger = useRef<HTMLButtonElement>(null);

  const activeId = chat.activeId;
  const openCitation: OpenCitation = useCallback(
    (citation, number, trigger) => {
      sourceTrigger.current = trigger;
      setOpened({ citation, number, conversationId: activeId });
    },
    [activeId],
  );
  // A source belongs to the conversation it was opened from.
  const source = opened && opened.conversationId === activeId ? opened : null;

  const lastItem = chat.items.at(-1);
  const growth = `${chat.items.length}:${chat.turn.answer.length}:${chat.turn.phase}:${lastItem?.key ?? ""}`;
  const endRef = useFollowEnd(growth, chat.activeId);

  const title = chat.conversation?.title ?? (chat.activeId ? "Conversation" : "New conversation");
  const messageCount = chat.conversation?.messages.length ?? 0;
  const missing = chat.conversationError instanceof ApiError && chat.conversationError.status === 404;
  const empty = chat.items.length === 0 && !chat.conversationLoading && chat.conversationError === null;
  const handoff = chat.status === "escalated";

  return (
    <div className={cn("transition-[padding] duration-200 motion-reduce:transition-none", source && "lg:pr-[26rem]")}>
      <div className="mx-auto w-full max-w-3xl">
        <Panel className="min-h-[calc(100dvh-14rem)]">
          <header className="mb-6 flex flex-wrap items-start justify-between gap-x-4 gap-y-3 border-b pb-5">
            <div className="min-w-0">
              <h1 className="font-heading text-4xl break-words sm:text-5xl">{title}</h1>
              <p className="mt-3 flex min-h-6 items-center" aria-live="polite">
                {statusLine(chat.status, messageCount) !== "" ? (
                  <span className="inline-flex items-center gap-2 rounded-full border px-3 py-0.5 font-mono text-xs text-muted-foreground">
                    {handoff ? <Headset className="size-3.5" aria-hidden /> : null}
                    {statusLine(chat.status, messageCount)}
                  </span>
                ) : null}
              </p>
            </div>
            <div className="flex gap-1 sm:-mr-2">
              <Button ref={historyTrigger} variant="ghost" size="sm" className="rounded-full" onClick={() => setHistoryOpen(true)}>
                <History aria-hidden />
                History
              </Button>
              <Button variant="ghost" size="sm" className="rounded-full" onClick={() => chat.open(null)} disabled={chat.activeId === null && chat.items.length === 0}>
                <Plus aria-hidden />
                New
              </Button>
            </div>
          </header>

          {handoff ? (
            <p className="mb-5 rounded-2xl border border-border-strong px-4 py-3 text-sm">
              <span className="font-medium">With a support agent.</span>{" "}
              <span className="text-muted-foreground">The assistant stays silent while they handle this. Your messages go to the agent.</span>
            </p>
          ) : null}

          {chat.conversationLoading ? (
            <p role="status" className="font-mono text-sm text-muted-foreground">
              Loading the conversation
            </p>
          ) : chat.conversationError ? (
            <div role="alert" className="space-y-3 text-sm">
              <p>
                {missing
                  ? "This conversation could not be found. It may belong to someone else or no longer exist."
                  : "The conversation could not be loaded."}
              </p>
              <div className="flex gap-2">
                {missing ? null : (
                  <Button variant="secondary" size="sm" onClick={chat.reloadConversation}>
                    Try again
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={() => chat.open(null)}>
                  Start a new conversation
                </Button>
              </div>
            </div>
          ) : empty ? (
            <div className="max-w-prose space-y-3 text-[0.9375rem]">
              <p className="text-[1.0625rem] font-medium">Ask a question about your account or your documents.</p>
              <p className="text-muted-foreground">
                Type it in the box below and press Enter. Answers point to the passages they come from. Anything that
                would change your account waits for your approval first. Earlier conversations are under History.
              </p>
            </div>
          ) : (
            <ThreadView items={chat.items} onOpenCitation={openCitation} onDecide={(approved) => void chat.decide(approved)} onRetry={chat.retry} />
          )}
          <div ref={endRef} aria-hidden className="scroll-mb-40" />
        </Panel>

        <Composer state={chat.composer} onSend={chat.send} onStop={chat.stop} />
      </div>

      <CitationPanel source={source} onClose={() => setOpened(null)} returnFocusTo={sourceTrigger} />
      <HistorySheet
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        history={chat.history}
        activeId={chat.activeId}
        onSelect={(id) => {
          chat.open(id);
          setHistoryOpen(false);
        }}
        onNew={() => {
          chat.open(null);
          setHistoryOpen(false);
        }}
        returnFocusTo={historyTrigger}
      />
    </div>
  );
}
