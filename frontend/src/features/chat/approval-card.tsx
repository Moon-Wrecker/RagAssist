import { Check, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { argumentRows } from "./argument-rows";
import type { PendingInterrupt } from "./types";
import type { DecisionOutcome, TurnError } from "./turn";

function Arguments({ args }: { args: unknown }) {
  const rows = argumentRows(args);
  if (rows.length === 0) return <p className="font-mono text-xs text-muted-foreground">No arguments.</p>;
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 font-mono text-[0.8125rem]">
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
 * An action that changes the account, paused until the person decides. It shows the tool and the exact arguments
 * the server stored with the interrupt. Which action runs is fixed on the server; this card only sends the decision.
 */
export function ApprovalCard({
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
    const card = ref.current;
    if (!card) return;
    card.focus({ preventScroll: true });
    // Centre it so the floating composer cannot cover the Approve and Deny buttons.
    card.scrollIntoView({ block: "center" });
  }, [interrupt.interruptId]);

  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="group"
      aria-labelledby="approval-title"
      className="my-5 rounded-3xl border border-border-strong p-5 focus:outline-none"
    >
      <p id="approval-title" className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
        Needs your approval
      </p>
      <p className="mt-2 text-sm">
        The assistant wants to run <span className="font-mono">{interrupt.tool}</span> with these values. Nothing happens until you decide.
      </p>
      <div className="mt-3 border-t pt-3">
        <Arguments args={interrupt.arguments} />
      </div>
      {error ? (
        <p role="alert" className="mt-3 text-sm">
          {error.message}
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" className="rounded-full" onClick={() => onDecide(true)} disabled={deciding} aria-label={`Approve ${interrupt.tool}`}>
          <Check aria-hidden />
          Approve
        </Button>
        <Button variant="secondary" size="sm" className="rounded-full" onClick={() => onDecide(false)} disabled={deciding} aria-label={`Deny ${interrupt.tool}`}>
          <X aria-hidden />
          Deny
        </Button>
        {deciding ? (
          <span role="status" className="self-center font-mono text-xs text-muted-foreground">
            Sending your decision
          </span>
        ) : null}
      </div>
    </div>
  );
}

/** What was decided, kept in the thread after the card is gone. */
export function DecisionLine({ outcome }: { outcome: DecisionOutcome }) {
  const rows = argumentRows(outcome.arguments);
  return (
    <div className="my-4 rounded-2xl border border-border-strong px-4 py-3 text-sm">
      <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-wide text-muted-foreground">
        {outcome.approved ? <Check className="size-3.5" aria-hidden /> : <X className="size-3.5" aria-hidden />}
        {outcome.approved ? "You approved" : "You denied"}
        <span className="normal-case tracking-normal text-foreground">{outcome.tool}</span>
      </p>
      {rows.length > 0 ? (
        <p className="mt-1 font-mono text-xs break-words text-muted-foreground">
          {rows.map((row) => `${row.name}: ${row.block ? "…" : row.value}`).join("   ")}
        </p>
      ) : null}
    </div>
  );
}
