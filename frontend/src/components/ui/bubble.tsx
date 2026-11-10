import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * shadcn AI Elements "Bubble" (MIT), kept to the one variant this app has: the person's own message as a small
 * thin-glass bubble. The outer radius is large and the corner toward the speaker is tighter, like the platform's
 * own message bubbles. Assistant text has no bubble.
 */
function Bubble({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="bubble" className={cn("relative flex w-fit max-w-[86%] min-w-0 flex-col", className)} {...props} />;
}

function BubbleContent({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="bubble-content"
      className={cn(
        "glass-thin w-fit max-w-full min-w-0 rounded-[1.25rem] rounded-br-md px-4 py-2.5 leading-relaxed wrap-break-word whitespace-pre-wrap",
        className,
      )}
      {...props}
    />
  );
}

export { Bubble, BubbleContent };
