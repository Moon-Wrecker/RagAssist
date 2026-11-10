import { Headset, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ApprovalCard, DecisionLine } from "./approval-card";
import { Markdown, type OpenCitation } from "./markdown";
import { sourceLocation } from "./source-location";
import type { ThreadItem } from "./thread";
import type { ThreadNote, TurnState } from "./turn";
import type { ChatMessage, Citation } from "./types";

function clock(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** The small mono line above each turn: who spoke and when. */
function Speaker({ name, at }: { name: string; at?: string | null }) {
  const time = clock(at ?? null);
  return (
    <p className="mb-1.5 font-mono text-xs uppercase tracking-wide text-muted-foreground">
      {name}
      {time ? <span className="ml-2 normal-case tracking-normal">{time}</span> : null}
    </p>
  );
}

const turnClass = "py-3 first:pt-0";

/** The customer's words as a plain typographic block, not a bubble. */
function UserTurn({ text, at }: { text: string; at?: string | null }) {
  return (
    <article className={cn(turnClass, "flex flex-col items-end")}>
      <Speaker name="You" at={at} />
      <p className="max-w-[88%] rounded-3xl rounded-tr-lg bg-foreground/[0.07] px-5 py-3 text-[1rem] leading-relaxed font-medium whitespace-pre-wrap break-words">
        {text}
      </p>
    </article>
  );
}

/** The sources of an answer as a list, so every one can be opened even when the text does not mark it. */
function Sources({ citations, onOpen }: { citations: readonly Citation[]; onOpen: OpenCitation }) {
  if (citations.length === 0) return null;
  return (
    <section aria-label="Sources" className="mt-4 pt-1">
      <h3 className="mb-1.5 font-mono text-xs uppercase tracking-wide text-muted-foreground">Sources</h3>
      <ol className="-mx-2 space-y-0.5">
        {citations.map((citation, index) => {
          const where = sourceLocation({ headingPath: citation.headingPath, page: citation.page });
          return (
            <li key={citation.chunkId}>
              <button
                type="button"
                onClick={(event) => onOpen(citation, index + 1, event.currentTarget)}
                className="group flex w-full items-baseline gap-3 rounded-2xl px-2 py-1.5 text-left font-mono text-xs hover:bg-accent"
              >
                <span className="shrink-0 rounded-full border border-border-strong px-2 py-0.5">{index + 1}</span>
                <span className="min-w-0 break-words">
                  <span className="underline-offset-4 group-hover:underline">{citation.title || "Untitled document"}</span>
                  {where ? <span className="text-muted-foreground">{`  ·  ${where}`}</span> : null}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function AnswerTurn({
  name,
  text,
  citations,
  at,
  onOpenCitation,
  streaming = false,
  children,
}: {
  name: string;
  text: string;
  citations: readonly Citation[];
  at?: string | null;
  onOpenCitation: OpenCitation;
  streaming?: boolean;
  children?: ReactNode;
}) {
  return (
    <article className={turnClass}>
      <Speaker name={name} at={at} />
      {/* aria-busy holds screen-reader updates until the answer is complete, then the whole text is read once. */}
      <div aria-live="polite" aria-busy={streaming}>
        {text !== "" ? (
          <div className="text-[0.9375rem] leading-relaxed break-words">
            <Markdown text={text} citations={citations} onOpenCitation={onOpenCitation} />
            {streaming ? (
              <span aria-hidden className="font-mono text-muted-foreground">
                ▍
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
      {children}
      {streaming ? null : <Sources citations={citations} onOpen={onOpenCitation} />}
    </article>
  );
}

function MessageTurn({ message, onOpenCitation }: { message: ChatMessage; onOpenCitation: OpenCitation }) {
  if (message.role === "user") return <UserTurn text={message.text} at={message.createdAt} />;
  return (
    <AnswerTurn
      name={message.role === "agent" ? "Support agent" : "Assistant"}
      text={message.text}
      citations={message.citations}
      at={message.createdAt}
      onOpenCitation={onOpenCitation}
    />
  );
}

export function HandoffLine({ ticketId }: { ticketId: string | null }) {
  return (
    <div className="my-4 flex items-start gap-3 rounded-2xl border border-border-strong px-4 py-3 text-sm">
      <Headset className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <p className="font-medium">A support agent has taken over</p>
        <p className="font-mono text-xs text-muted-foreground">
          {ticketId ? `Ticket ${ticketId}  ·  ` : ""}The assistant stays silent. Your messages go to the agent.
        </p>
      </div>
    </div>
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
    <>
      <UserTurn text={turn.question} />
      {showAnswer ? (
        <AnswerTurn
          name="Assistant"
          text={turn.answer}
          citations={turn.citations}
          onOpenCitation={onOpenCitation}
          streaming={streaming && turn.answer !== ""}
        >
          {turn.tools.length > 0 ? (
            <ul aria-label="Steps" className="mb-2 space-y-0.5 font-mono text-xs text-muted-foreground">
              {turn.tools.map((tool, index) => (
                <li key={`${tool.tool}-${index}`}>
                  <span aria-hidden>{tool.status === "completed" ? "● " : "○ "}</span>
                  {tool.status === "completed" ? "Used" : "Using"} {tool.tool}
                </li>
              ))}
            </ul>
          ) : null}
          {waiting ? (
            <p role="status" className="font-mono text-sm text-muted-foreground">
              Looking through your documents
            </p>
          ) : null}
        </AnswerTurn>
      ) : null}
      {needsDecision && turn.interrupt ? (
        <ApprovalCard interrupt={turn.interrupt} deciding={turn.phase === "deciding"} error={turn.error} onDecide={onDecide} />
      ) : null}
      {turn.outcome && !needsDecision ? <DecisionLine outcome={turn.outcome} /> : null}
      {turn.escalation && !turn.wasEscalated ? <HandoffLine ticketId={turn.escalation.ticketId} /> : null}
      {turn.stopped ? (
        <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-xs text-muted-foreground">
          <span>Stopped. The assistant may still finish and save this answer.</span>
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <RotateCcw aria-hidden />
            Ask again
          </Button>
        </div>
      ) : null}
      {turn.error && turn.error.kind !== "decision" ? (
        <div role="alert" className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-border-strong px-4 py-3 text-sm">
          <span>{turn.error.message}</span>
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <RotateCcw aria-hidden />
            Try again
          </Button>
        </div>
      ) : null}
    </>
  );
}

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
    <div>
      {items.map((item) => {
        switch (item.kind) {
          case "message":
            return <MessageTurn key={item.key} message={item.message} onOpenCitation={onOpenCitation} />;
          case "note":
            return <NoteView key={item.key} note={item.note} />;
          case "live":
            return (
              <LiveTurnView key={item.key} turn={item.turn} onOpenCitation={onOpenCitation} onDecide={onDecide} onRetry={onRetry} />
            );
        }
      })}
    </div>
  );
}
