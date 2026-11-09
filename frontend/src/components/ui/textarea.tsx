import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        // 16px on phones stops iOS from zooming the page on focus.
        "min-h-20 w-full min-w-0 resize-y rounded-md border border-input bg-foreground/[0.04] px-3 py-2 text-base transition-colors placeholder:text-muted-foreground focus-visible:border-foreground disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-foreground aria-invalid:border-dashed md:text-sm",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
