import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * shadcn "Input Group", the base of the AI Elements Prompt Input (https://ui.shadcn.com/docs/ai-elements/base/prompt-input,
 * MIT). The group is the glass object: the textarea inside is transparent and borderless, addons sit above or below
 * it. The radius is set by the caller (--r-outer) and children take outer minus padding (.r-inner).
 */
function InputGroup({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="input-group"
      role="group"
      className={cn(
        "relative flex w-full min-w-0 flex-col has-[[data-slot=input-group-control]:focus-visible]:outline-2 has-[[data-slot=input-group-control]:focus-visible]:outline-offset-2 has-[[data-slot=input-group-control]:focus-visible]:outline-ring",
        className,
      )}
      {...props}
    />
  );
}

function InputGroupAddon({ className, align = "block-end", ...props }: ComponentProps<"div"> & { align?: "block-start" | "block-end" | "inline-end" }) {
  return (
    <div
      data-slot="input-group-addon"
      data-align={align}
      className={cn("flex items-center gap-2 data-[align=block-end]:justify-between", className)}
      {...props}
    />
  );
}

function InputGroupTextarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="input-group-control"
      className={cn(
        "scroll-area w-full min-w-0 flex-1 resize-none bg-transparent px-1 py-1 text-base leading-relaxed outline-none placeholder:text-muted-foreground aria-disabled:opacity-60 md:text-[0.9375rem]",
        className,
      )}
      {...props}
    />
  );
}

export { InputGroup, InputGroupAddon, InputGroupTextarea };
