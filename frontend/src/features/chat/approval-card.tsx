import { Check, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Trace, TraceIcon, TraceLine, TraceTitle } from "@/components/ui/trace";
import { argumentRows } from "./argument-rows";
import type { PendingInterrupt } from "./types";
import type { DecisionOutcome, TurnError } from "./turn";

function Arguments({ args }: { args: unknown }) {
  const rows = argumentRows(args);
  if (rows.length === 0) return <p className="text-meta text-muted-foreground">No arguments.</p>;
  return (
    <dl className="text-meta grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
      {rows.map((row) => (
        <div key={row.name} className="contents">
          <dt className="text-muted-foreground">{row.name}</dt>
          <dd className={row.block ? "whitespace-pre-wrap break-words" : "break-words"}>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * An action that changes the account, paused until the person decides: an inline row on a hairline rule (the AI
 * Elements Confirmation pattern as a Trace, never a card). It shows the tool and the exact arguments the server
 * stored with the interrupt. Which action runs is fixed on the server; this row only sends the decision.
 */
export function ApprovalRow({
  interrupt,
  deciding,
  error,
  onDecide,
}: {
  interrupt: PendingInterrupt;
  deciding: boolean;
  error: TurnError | null;
  onDecide: (approved: boolean) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // The composer is locked until this is decided, so move attention here when it appears.
  useEffect(() => {
    const row = ref.current;
    if (!row) return;
    row.focus({ preventScroll: true });
    // Centre it so the floating composer cannot cover the Approve and Deny buttons.
    row.scrollIntoView({ block: "center" });
  }, [interrupt.interruptId]);

  return (
    <div ref={ref} tabIndex={-1} role="group" aria-labelledby="approval-title" className="focus:outline-none">
      <Trace className="gap-3 border-foreground/60">
        <p id="approval-title" className="text-meta text-muted-foreground">
          Needs your approval
        </p>
        <p className="text-sm">
          The assistant wants to run <span className="font-mono text-[0.875em]">{interrupt.tool}</span>. Nothing happens until you decide.
        </p>
        <Arguments args={interrupt.arguments} />
        {error ? (
          <p role="alert" className="text-sm">
            {error.message}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button size="sm" onClick={() => onDecide(true)} disabled={deciding} aria-label={`Approve ${interrupt.tool}`}>
            <Check aria-hidden />
            Approve
          </Button>
          <Button variant="secondary" size="sm" onClick={() => onDecide(false)} disabled={deciding} aria-label={`Deny ${interrupt.tool}`}>
            <X aria-hidden />
            Deny
          </Button>
          {deciding ? (
            <span role="status" className="text-meta text-muted-foreground">
              Sending your decision
            </span>
          ) : null}
        </div>
      </Trace>
    </div>
  );
}

/** What was decided, kept in the thread after the row is gone. */
export function DecisionLine({ outcome }: { outcome: DecisionOutcome }) {
  const rows = argumentRows(outcome.arguments);
  return (
    <Trace>
      <TraceLine>
        <TraceIcon>{outcome.approved ? <Check /> : <X />}</TraceIcon>
        <TraceTitle className="text-foreground">
          {outcome.approved ? "You approved" : "You denied"} <span className="font-mono text-[0.875em]">{outcome.tool}</span>
        </TraceTitle>
      </TraceLine>
      {rows.length > 0 ? (
        <p className="text-meta break-words text-muted-foreground">
          {rows.map((row) => `${row.name}: ${row.block ? "…" : row.value}`).join("   ")}
        </p>
      ) : null}
    </Trace>
  );
}
