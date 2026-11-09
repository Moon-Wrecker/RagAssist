import { ChevronDown } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * A native select with the app's field styling. Native keeps full keyboard and screen-reader behaviour, and the
 * platform's own picker on phones. Always give it an accessible name (`aria-label` or a Label).
 */
function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <div className="relative inline-flex w-full">
      <select
        className={cn(
          "h-10 w-full min-w-0 appearance-none rounded-md border border-input bg-foreground/[0.04] py-0 pr-9 pl-3 text-base transition-colors focus-visible:border-foreground disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown aria-hidden className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground" />
    </div>
  );
}

export { Select };
