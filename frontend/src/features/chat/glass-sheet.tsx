import { X } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { AnimatePresence, motion } from "motion/react";
import type { ReactNode, RefObject } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type SheetPlacement = "left" | "right" | "bottom";

const placementClass: Record<SheetPlacement, string> = {
  left: "inset-y-3 left-3 w-[min(22rem,calc(100vw-1.5rem))] rounded-(--r-bar)",
  right: "inset-y-3 right-3 w-[min(26rem,calc(100vw-1.5rem))] rounded-(--r-bar)",
  bottom: "inset-x-(--gutter) bottom-(--gutter) max-h-[78dvh] rounded-(--r-bar)",
};

const placementMotion: Record<SheetPlacement, { x?: string; y?: string }> = {
  left: { x: "-110%" },
  right: { x: "110%" },
  bottom: { y: "100%" },
};

/**
 * A glass layer that slides in from an edge: the history slide-over and the citation panel. Built on Radix Dialog,
 * so Escape closes it and focus is managed. `modal` adds the scrim and a focus trap; the citation panel is
 * non-modal on desktop so the thread stays usable beside it. On close, focus returns to `returnFocusTo`.
 */
export function GlassSheet({
  open,
  onOpenChange,
  placement,
  modal = true,
  title,
  description,
  returnFocusTo,
  children,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  placement: SheetPlacement;
  modal?: boolean;
  title: ReactNode;
  description: string;
  returnFocusTo?: RefObject<HTMLElement | null>;
  children: ReactNode;
  className?: string;
}) {
  const offscreen = placementMotion[placement];
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange} modal={modal}>
      <AnimatePresence>
        {open ? (
          <DialogPrimitive.Portal forceMount>
            {modal ? (
              <DialogPrimitive.Overlay asChild forceMount>
                <motion.div
                  className="fixed inset-0 z-50 bg-scrim"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.14 }}
                />
              </DialogPrimitive.Overlay>
            ) : null}
            <DialogPrimitive.Content
              asChild
              forceMount
              // A non-modal panel does not close when the person clicks the thread, so they can open another source.
              onInteractOutside={modal ? undefined : (event) => event.preventDefault()}
              onCloseAutoFocus={(event) => {
                if (!returnFocusTo) return;
                event.preventDefault();
                returnFocusTo.current?.focus();
              }}
            >
              <motion.div
                className={cn(
                  "glass-thick fixed z-50 flex flex-col text-popover-foreground",
                  placementClass[placement],
                  className,
                )}
                initial={{ opacity: 0, ...offscreen }}
                animate={{ opacity: 1, x: 0, y: 0 }}
                exit={{ opacity: 0, ...offscreen }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                <div className="flex items-start justify-between gap-3 p-5 pb-3">
                  <div className="min-w-0">
                    <DialogPrimitive.Title className="text-meta text-muted-foreground">
                      {title}
                    </DialogPrimitive.Title>
                    <DialogPrimitive.Description className="sr-only">{description}</DialogPrimitive.Description>
                  </div>
                  <DialogPrimitive.Close asChild>
                    <Button variant="ghost" size="icon-sm" aria-label="Close" className="-mt-2 -mr-2 shrink-0">
                      <X aria-hidden />
                    </Button>
                  </DialogPrimitive.Close>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-6">{children}</div>
              </motion.div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        ) : null}
      </AnimatePresence>
    </DialogPrimitive.Root>
  );
}
