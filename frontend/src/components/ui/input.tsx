import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(
        // 16px on phones stops iOS from zooming the page on focus.
        "h-10 w-full min-w-0 rounded-md border border-input bg-transparent px-3 text-base transition-colors placeholder:text-muted-foreground focus-visible:border-foreground disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-foreground aria-invalid:border-dashed md:text-sm",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
