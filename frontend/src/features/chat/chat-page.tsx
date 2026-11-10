import { History, Plus } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiError } from "@/api/errors";
import { PageFrame } from "@/components/page-frame";
import { Button } from "@/components/ui/button";
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { CitationPanel, type OpenSource } from "./citation-panel";
import { Composer } from "./composer";
import { HistorySheet } from "./history-sheet";
import type { OpenCitation } from "./markdown";
import { ThreadView } from "./thread-view";
import { useChat } from "./use-chat";

function greeting(now = new Date()): string {
  const hour = now.getHours();
  if (hour < 5) return "Still up?";
  if (hour < 12) return "Good morning.";
  if (hour < 18) return "Good afternoon.";
  return "Good evening.";
}

/** Height of the greeting block above the centred composer, and the gap between them (px). */
const GREETING_BLOCK = 64;
const GREETING_GAP = 24;

function statusLine(status: string | undefined, messageCount: number): string {
  const parts: string[] = [];
  if (status === "escalated") parts.push("With a support agent");
  else if (status === "resolved") parts.push("Resolved");
  if (messageCount > 0) parts.push(`${messageCount} ${messageCount === 1 ? "message" : "messages"}`);
  return parts.join("  ·  ");
}

/** Tracks the size of an element without per-frame React work: one state update per real resize. */
function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const read = () => setSize((current) => (current.width === element.offsetWidth && current.height === element.offsetHeight ? current : { width: element.offsetWidth, height: element.offsetHeight }));
    read();
    const observer = new ResizeObserver(read);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, size] as const;
}

/**
 * Chat. Empty: a short serif greeting with the composer directly under it, centred. On the first send the composer
 * glides down to its docked place at the bottom and the greeting fades out. Conversation: one 44rem column directly
 * on the page (no boxes); only the message list scrolls, and it scrolls under the glass header and composer.
 */
export function ChatPage() {
  const chat = useChat();
  const [opened, setOpened] = useState<(OpenSource & { conversationId: string | null }) | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const sourceTrigger = useRef<HTMLElement | null>(null);
  const historyTrigger = useRef<HTMLButtonElement>(null);
  const [areaRef, area] = useSize<HTMLDivElement>();
  const [composerRef, composer] = useSize<HTMLDivElement>();
  // The room the page keeps below its content (the gutter, or the tab bar on a phone), measured in px.
  const [floorRef, floor] = useSize<HTMLDivElement>();

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

  const title = chat.conversation?.title ?? (chat.activeId ? "Conversation" : "New conversation");
  const messageCount = chat.conversation?.messages.length ?? 0;
  const missing = chat.conversationError instanceof ApiError && chat.conversationError.status === 404;
  const empty = chat.items.length === 0 && !chat.conversationLoading && chat.conversationError === null && chat.activeId === null;
  const status = statusLine(chat.status, messageCount);

  // Where the composer rests when the chat is empty, as an offset from its docked place.
  const measured = area.height > 0 && composer.height > 0;
  const group = GREETING_BLOCK + GREETING_GAP + composer.height;
  const centredTop = (area.height - floor.height - group) / 2 + GREETING_BLOCK + GREETING_GAP;
  const dockedTop = area.height - composer.height - floor.height - 12;
  const restOffset = Math.min(0, centredTop - dockedTop);

  const [hello] = useState(() => greeting());
  const panelOpen = source !== null;

  // Keep the document from scrolling when focus moves into the composer on a phone keyboard.
  useEffect(() => {
    const onFocus = () => window.scrollTo(0, 0);
    window.addEventListener("focusin", onFocus);
    return () => window.removeEventListener("focusin", onFocus);
  }, []);

  return (
    <PageFrame
      mode="bleed"
      plainTitle
      title={
        <span className="flex min-w-0 items-baseline gap-3">
          <span className="truncate">{title}</span>
          {status !== "" ? (
            <span className="text-meta shrink-0 font-normal text-muted-foreground" aria-live="polite">
              {status}
            </span>
          ) : null}
        </span>
      }
      actions={
        <div className="flex gap-1 md:hidden">
          <Button ref={historyTrigger} variant="ghost" size="sm" onClick={() => setHistoryOpen(true)}>
            <History aria-hidden />
            History
          </Button>
          <Button variant="ghost" size="sm" onClick={() => chat.open(null)} disabled={chat.activeId === null && chat.items.length === 0}>
            <Plus aria-hidden />
            New
          </Button>
        </div>
      }
    >
      <div ref={areaRef} className="relative h-full">
        <div ref={floorRef} aria-hidden className="pointer-events-none absolute bottom-0 left-0 h-(--page-bottom) w-px" />
        {/* The message list: the only scroller. It is padded so the first message starts below the header and the last
            one can rest above the composer; everything between passes under the glass. */}
        {!empty ? (
          <MessageScrollerProvider key={activeId ?? "new"} autoScroll defaultScrollPosition="end">
            <MessageScroller className="absolute inset-0">
              <MessageScrollerViewport
                className={cn("pt-[calc(var(--gutter)*2+var(--header-h)+1rem)]", panelOpen && "lg:pr-[26rem]")}
                style={{ paddingBottom: composer.height + floor.height + 12 + 32 }}
              >
                {chat.conversationLoading ? (
                  <p role="status" className="text-meta mx-auto w-full max-w-(--chat-max) px-4 text-muted-foreground">
                    Loading the conversation
                  </p>
                ) : chat.conversationError ? (
                  <div role="alert" className="mx-auto w-full max-w-(--chat-max) space-y-3 px-4 text-sm">
                    <p>{missing ? "This conversation could not be found." : "The conversation could not be loaded."}</p>
                    <div className="flex gap-2">
                      {missing ? null : (
                        <Button variant="secondary" size="sm" onClick={chat.reloadConversation}>
                          Try again
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" onClick={() => chat.open(null)}>
                        Start a new conversation
                      </Button>
                    </div>
                  </div>
                ) : (
                  <MessageScrollerContent className="mx-auto w-full max-w-(--chat-max) gap-8 px-4" aria-busy={chat.busy}>
                    <ThreadView items={chat.items} onOpenCitation={openCitation} onDecide={(approved) => void chat.decide(approved)} onRetry={chat.retry} />
                  </MessageScrollerContent>
                )}
              </MessageScrollerViewport>
              <MessageScrollerButton style={{ bottom: composer.height + floor.height + 12 + 16 }} />
            </MessageScroller>
          </MessageScrollerProvider>
        ) : null}

        <AnimatePresence>
          {empty && measured ? (
            <motion.h2
              key="greeting"
              className="font-greeting pointer-events-none absolute inset-x-0 text-center"
              style={{ top: centredTop - GREETING_BLOCK - GREETING_GAP, height: GREETING_BLOCK, lineHeight: `${GREETING_BLOCK}px` }}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              {hello}
            </motion.h2>
          ) : null}
        </AnimatePresence>

        {/* The composer is one element for good: docked at the bottom, offset up to the middle while the chat is empty. */}
        <motion.div
          className={cn("absolute inset-x-0 bottom-[calc(var(--page-bottom)+0.75rem)] z-10 px-4", panelOpen && "lg:pr-[27rem]", !measured && "invisible")}
          initial={false}
          animate={{ y: empty ? restOffset : 0 }}
          transition={spring.glide}
        >
          <div ref={composerRef} className="mx-auto w-full max-w-(--chat-max)">
            <Composer state={chat.composer} onSend={chat.send} onStop={chat.stop} autoFocus={empty} />
          </div>
        </motion.div>
      </div>

      <CitationPanel source={source} onClose={() => setOpened(null)} returnFocusTo={sourceTrigger} />
      <HistorySheet
        open={historyOpen}
        onOpenChange={setHistoryOpen}
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
    </PageFrame>
  );
}
