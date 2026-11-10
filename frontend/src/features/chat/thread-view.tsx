import { Headset, RotateCcw } from "lucide-react";
import { memo, type ReactNode } from "react";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import { Message, MessageContent, MessageFooter, MessageHeader } from "@/components/ui/message";
import { MessageScrollerItem } from "@/components/ui/message-scroller";
import { Trace, TraceDescription, TraceIcon, TraceLine, TraceTitle } from "@/components/ui/trace";
import { cn } from "@/lib/utils";
import { ApprovalRow, DecisionLine } from "./approval-card";
import { Markdown, type OpenCitation } from "./markdown";
import { sourceLocation } from "./source-location";
import type { ThreadItem } from "./thread";
import type { ThreadNote, TurnState } from "./turn";
import type { ChatMessage, Citation } from "./types";

function clock(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** The person's words: a small thin-glass bubble on the right. */
function UserTurn({ text }: { text: string }) {
  return (
    <Message align="end">
      <MessageContent>
        <Bubble>
          <BubbleContent>{text}</BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  );
}

/** The sources of an answer as a compact row of mono chips; each one opens the passage in the citation panel. */
function Sources({ citations, onOpen }: { citations: readonly Citation[]; onOpen: OpenCitation }) {
  if (citations.length === 0) return null;
  return (
    <MessageFooter aria-label="Sources" role="group" className="pt-1">
      {citations.map((citation, index) => {
        const where = sourceLocation({ headingPath: citation.headingPath, page: citation.page });
        const name = citation.title || "Untitled document";
        return (
          <button
            key={citation.chunkId}
            type="button"
            onClick={(event) => onOpen(citation, index + 1, event.currentTarget)}
            title={where ? `${name} · ${where}` : name}
            className="glass-thin press text-meta inline-flex h-7 max-w-[15rem] items-center gap-1.5 rounded-full px-2.5 text-foreground"
          >
            <span>{index + 1}</span>
            <span className="truncate text-muted-foreground">{name}</span>
          </button>
        );
      })}
    </MessageFooter>
  );
}

function AnswerTurn({
  name,
  text,
  citations,
  at,
  onOpenCitation,
  streaming = false,
  before,
  after,
}: {
  name: string | null;
  text: string;
  citations: readonly Citation[];
  at?: string | null;
  onOpenCitation: OpenCitation;
  streaming?: boolean;
  before?: ReactNode;
  after?: ReactNode;
}) {
  return (
    <Message>
      <MessageContent>
        {name ? (
          <MessageHeader>
            <span>{name}</span>
            {clock(at) ? <span>{clock(at)}</span> : null}
          </MessageHeader>
        ) : null}
        {before}
        {/* aria-busy holds screen-reader updates until the answer is complete, then the whole text is read once. */}
        <div aria-live="polite" aria-busy={streaming}>
          {text !== "" ? (
            <Markdown
              text={text}
              citations={citations}
              onOpenCitation={onOpenCitation}
              className={cn("text-[0.9375rem] leading-[1.6] break-words", streaming && "[&>*:last-child]:fade-in")}
            />
          ) : null}
        </div>
        {after}
        {streaming ? null : <Sources citations={citations} onOpen={onOpenCitation} />}
      </MessageContent>
    </Message>
  );
}

const MessageTurn = memo(function MessageTurn({ message, onOpenCitation }: { message: ChatMessage; onOpenCitation: OpenCitation }) {
  if (message.role === "user") return <UserTurn text={message.text} />;
  return (
    <AnswerTurn
      name={message.role === "agent" ? "Support agent" : null}
      text={message.text}
      citations={message.citations}
      at={message.createdAt}
      onOpenCitation={onOpenCitation}
    />
  );
});

export function HandoffLine({ ticketId }: { ticketId: string | null }) {
  return (
    <Trace>
      <TraceLine>
        <TraceIcon>
          <Headset />
        </TraceIcon>
        <TraceTitle className="text-foreground">A support agent has taken over</TraceTitle>
      </TraceLine>
      <TraceLine className="text-meta">{ticketId ? `Ticket ${ticketId}` : "Your messages now go to the agent."}</TraceLine>
    </Trace>
  );
}

function NoteView({ note }: { note: ThreadNote }) {
  return note.kind === "decision" ? <DecisionLine outcome={note.outcome} /> : <HandoffLine ticketId={note.ticketId} />;
}

function LiveTurnView({
  turn,
  onOpenCitation,
  onDecide,
  onRetry,
}: {
  turn: TurnState;
  onOpenCitation: OpenCitation;
  onDecide: (approved: boolean) => void;
  onRetry: () => void;
}) {
  const streaming = turn.phase === "streaming";
  const waiting = streaming && turn.answer === "";
  const showAnswer = turn.answer !== "" || waiting || turn.tools.length > 0;
  const needsDecision = turn.phase === "interrupted" || turn.phase === "deciding";

  return (
    <div className="flex flex-col gap-8">
      <UserTurn text={turn.question} />
      {showAnswer ? (
        <AnswerTurn
          name={null}
          text={turn.answer}
          citations={turn.citations}
          onOpenCitation={onOpenCitation}
          streaming={streaming && turn.answer !== ""}
          before={
            turn.tools.length > 0 ? (
              <Trace aria-label="Steps" role="list">
                {turn.tools.map((tool, index) => (
                  <TraceLine key={`${tool.tool}-${index}`} role="listitem" status={tool.status === "completed" ? "done" : "running"}>
                    <TraceIcon>{tool.status === "completed" ? "●" : "○"}</TraceIcon>
                    <TraceTitle>
                      {tool.status === "completed" ? "Used" : "Using"} {tool.tool}
                    </TraceTitle>
                  </TraceLine>
                ))}
              </Trace>
            ) : null
          }
          after={
            waiting ? (
              <p role="status" className="shimmer w-fit text-[0.9375rem]">
                Looking through your documents
              </p>
            ) : null
          }
        />
      ) : null}
      {needsDecision && turn.interrupt ? (
        <ApprovalRow interrupt={turn.interrupt} deciding={turn.phase === "deciding"} error={turn.error} onDecide={onDecide} />
      ) : null}
      {turn.outcome && !needsDecision ? <DecisionLine outcome={turn.outcome} /> : null}
      {turn.escalation && !turn.wasEscalated ? <HandoffLine ticketId={turn.escalation.ticketId} /> : null}
      {turn.stopped ? (
        <Trace>
          <TraceLine className="text-meta flex-wrap">
            <TraceTitle className="whitespace-normal">Stopped. The assistant may still finish and save this answer.</TraceTitle>
            <Button variant="ghost" size="sm" onClick={onRetry}>
              <RotateCcw aria-hidden />
              Ask again
            </Button>
          </TraceLine>
        </Trace>
      ) : null}
      {turn.error && turn.error.kind !== "decision" ? (
        <Trace role="alert">
          <TraceLine className="flex-wrap text-foreground">
            <TraceTitle className="whitespace-normal">{turn.error.message}</TraceTitle>
            <TraceDescription>
              <Button variant="ghost" size="sm" onClick={onRetry}>
                <RotateCcw aria-hidden />
                Try again
              </Button>
            </TraceDescription>
          </TraceLine>
        </Trace>
      ) : null}
    </div>
  );
}

/** The thread's rows, each one a Message Scroller item. Finished messages are memoised, so a stream re-renders only the live turn. */
export function ThreadView({
  items,
  onOpenCitation,
  onDecide,
  onRetry,
}: {
  items: readonly ThreadItem[];
  onOpenCitation: OpenCitation;
  onDecide: (approved: boolean) => void;
  onRetry: () => void;
}) {
  return (
    <>
      {items.map((item) => (
        <MessageScrollerItem key={item.key} messageId={item.key}>
          {item.kind === "message" ? (
            <MessageTurn message={item.message} onOpenCitation={onOpenCitation} />
          ) : item.kind === "note" ? (
            <NoteView note={item.note} />
          ) : (
            <LiveTurnView turn={item.turn} onOpenCitation={onOpenCitation} onDecide={onDecide} onRetry={onRetry} />
          )}
        </MessageScrollerItem>
      ))}
    </>
  );
}
