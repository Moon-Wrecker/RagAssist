import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * shadcn "Trace" (https://ui.shadcn.com/docs/ai-elements/base/tool, MIT), the base of the AI Elements Tool and
 * Confirmation patterns, as inline rows: an icon and a title on a hairline left rule, never a card. A running line
 * shimmers (the title only); a pending one is dimmed.
 */
function Trace({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="trace" className={cn("flex w-full min-w-0 flex-col gap-1.5 border-l pl-4", className)} {...props} />;
}

function TraceLine({ className, status, ...props }: ComponentProps<"div"> & { status?: "running" | "pending" | "done" | "error" }) {
  return (
    <div
      data-slot="trace-line"
      data-status={status}
      className={cn(
        "flex w-fit max-w-full min-w-0 items-center gap-2 text-sm text-muted-foreground data-[status=pending]:opacity-60 data-[status=running]:*:data-[slot=trace-title]:shimmer",
        className,
      )}
      {...props}
    />
  );
}

function TraceIcon({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      data-slot="trace-icon"
      aria-hidden
      className={cn("flex size-4 shrink-0 items-center justify-center [&_svg]:size-3.5", className)}
      {...props}
    />
  );
}

function TraceTitle({ className, ...props }: ComponentProps<"span">) {
  return <span data-slot="trace-title" className={cn("min-w-0 truncate", className)} {...props} />;
}

function TraceDescription({ className, ...props }: ComponentProps<"span">) {
  return <span data-slot="trace-description" className={cn("text-meta shrink-0 text-muted-foreground", className)} {...props} />;
}

export { Trace, TraceLine, TraceIcon, TraceTitle, TraceDescription };
