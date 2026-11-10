import {
  MessageScroller as MessageScrollerPrimitive,
  useMessageScroller,
  useMessageScrollerScrollable,
} from "@shadcn/react/message-scroller";
import { ArrowDown } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

/**
 * shadcn "Message Scroller" (@shadcn/react 0.3.1, MIT; https://ui.shadcn.com/docs/components/base/message-scroller)
 * on our tokens. It owns the chat scrolling: with `autoScroll` the view follows the stream while the reader is at
 * the live edge and lets go as soon as they scroll up; the button then offers a jump back. Only the viewport
 * scrolls (contained, stable gutter, thin bar); the composer and the header float over it.
 */
function MessageScrollerProvider(props: ComponentProps<typeof MessageScrollerPrimitive.Provider>) {
  return <MessageScrollerPrimitive.Provider {...props} />;
}

function MessageScroller({ className, ...props }: ComponentProps<typeof MessageScrollerPrimitive.Root>) {
  return <MessageScrollerPrimitive.Root data-slot="message-scroller" className={cn("relative size-full min-h-0", className)} {...props} />;
}

function MessageScrollerViewport({ className, ...props }: ComponentProps<typeof MessageScrollerPrimitive.Viewport>) {
  return (
    <MessageScrollerPrimitive.Viewport
      data-slot="message-scroller-viewport"
      className={cn("scroll-area absolute inset-0 size-full data-[pending-scroll]:invisible", className)}
      {...props}
    />
  );
}

function MessageScrollerContent({ className, ...props }: ComponentProps<typeof MessageScrollerPrimitive.Content>) {
  return <MessageScrollerPrimitive.Content data-slot="message-scroller-content" className={cn("flex h-max min-h-full flex-col", className)} {...props} />;
}

function MessageScrollerItem({ className, ...props }: ComponentProps<typeof MessageScrollerPrimitive.Item>) {
  return <MessageScrollerPrimitive.Item data-slot="message-scroller-item" className={cn("min-w-0 shrink-0", className)} {...props} />;
}

/** "Jump to latest": a small glass capsule that fades and scales in only while there is more below. */
function MessageScrollerButton({ className, children, ...props }: ComponentProps<typeof MessageScrollerPrimitive.Button>) {
  return (
    <MessageScrollerPrimitive.Button
      data-slot="message-scroller-button"
      direction="end"
      className={cn(
        "glass-thin press absolute left-1/2 z-10 -translate-x-1/2 text-label transition-[opacity,scale] duration-(--dur-base) ease-(--ease-out) data-[active=false]:pointer-events-none data-[active=false]:scale-95 data-[active=false]:opacity-0",
        className,
      )}
      render={<Button variant="secondary" size="sm" />}
      {...props}
    >
      {children ?? (
        <>
          <ArrowDown aria-hidden />
          Jump to latest
        </>
      )}
    </MessageScrollerPrimitive.Button>
  );
}

export {
  MessageScrollerProvider,
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
  useMessageScroller,
  useMessageScrollerScrollable,
};
