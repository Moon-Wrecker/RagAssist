import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * The thick glass surface a table sits on. It is a flex column that fills the room it is given; the table scrolls
 * inside it (contained, thin bar) and its sticky header stays put. No cards inside it.
 */
export function TableSurface({ className, children, ...props }: ComponentProps<"section">) {
  return (
    <section className={cn("glass-thick flex min-h-0 flex-col overflow-hidden rounded-(--r-surface)", className)} {...props}>
      <div className="scroll-area min-h-0 flex-1">{children}</div>
    </section>
  );
}
