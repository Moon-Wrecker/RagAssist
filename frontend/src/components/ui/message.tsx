import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * shadcn AI Elements "Message" (https://ui.shadcn.com/docs/ai-elements/base/message, MIT), reduced to the parts this
 * app uses and set on our tokens. Presentational only: it knows nothing about the chat reducer.
 */
function Message({ className, align = "start", ...props }: ComponentProps<"div"> & { align?: "start" | "end" }) {
  return (
    <div
      data-slot="message"
      data-align={align}
      className={cn("group/message relative flex w-full min-w-0 data-[align=end]:flex-row-reverse", className)}
      {...props}
    />
  );
}

function MessageContent({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="message-content"
      className={cn("flex w-full min-w-0 flex-col gap-2 wrap-break-word group-data-[align=end]/message:items-end", className)}
      {...props}
    />
  );
}

function MessageHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="message-header"
      className={cn("text-meta flex max-w-full min-w-0 items-center gap-2 text-muted-foreground group-data-[align=end]/message:justify-end", className)}
      {...props}
    />
  );
}

function MessageFooter({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="message-footer" className={cn("flex max-w-full min-w-0 flex-wrap items-center gap-1.5", className)} {...props} />;
}

export { Message, MessageContent, MessageHeader, MessageFooter };
