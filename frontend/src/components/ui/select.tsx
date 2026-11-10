import { ChevronDown } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * A native select. Native keeps full keyboard and screen-reader behaviour, and the platform's own picker on phones.
 * `inline` is the borderless form for a table cell (a role in a row): it looks like text until it is hovered or
 * focused. Always give it an accessible name (`aria-label` or a Label).
 */
function Select({ className, children, inline = false, ...props }: ComponentProps<"select"> & { inline?: boolean }) {
  return (
    <div className={cn("relative inline-flex", inline ? "w-fit" : "w-full")}>
      <select
        className={cn(
          inline
            ? "h-8 w-full min-w-0 appearance-none rounded-full bg-transparent py-0 pr-8 pl-3 text-sm transition-colors hover:bg-accent focus-visible:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
            : "h-10 w-full min-w-0 appearance-none rounded-xl border border-input bg-foreground/[0.04] py-0 pr-10 pl-4 text-base transition-colors focus-visible:border-foreground disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className={cn("pointer-events-none absolute top-1/2 -translate-y-1/2 text-muted-foreground", inline ? "right-2 size-3.5" : "right-3 size-4")}
      />
    </div>
  );
}

export { Select };
