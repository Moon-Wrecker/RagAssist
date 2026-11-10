import type { EventsStatus } from "@/events/use-events";
import { cn } from "@/lib/utils";

/** Filled dot when the live stream is connected, hollow dot with a word when it is not. Shape, not colour. */
export function LiveStatus({ status, className }: { status: EventsStatus; className?: string }) {
  const connected = status === "connected";
  const word = connected ? "Live updates on" : status === "idle" ? "Live updates off" : "Reconnecting";
  return (
    <span
      className={cn("text-meta inline-flex items-center gap-1.5 text-muted-foreground", className)}
      role="status"
      title={connected ? "Live updates on" : "Live updates off or reconnecting"}
    >
      <span aria-hidden>{connected ? "●" : "○"}</span>
      <span aria-hidden>{connected ? "Live" : status === "idle" ? "Offline" : "Reconnecting"}</span>
      <span className="sr-only">{word}</span>
    </span>
  );
}
