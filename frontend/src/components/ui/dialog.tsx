import { Dialog as DialogPrimitive } from "radix-ui";
import { AnimatePresence, motion } from "motion/react";
import { createContext, use, useState, type ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * shadcn's Dialog, animated with Motion instead of CSS keyframes. The wrapper tracks the open state so the
 * content can stay mounted for its exit animation. Motion's `MotionConfig reducedMotion="user"` (set in the app
 * root) turns the movement off for people who ask for reduced motion.
 */
const OpenContext = createContext(false);

function Dialog({ open, defaultOpen = false, onOpenChange, ...props }: ComponentProps<typeof DialogPrimitive.Root>) {
  const [inner, setInner] = useState(defaultOpen);
  const isOpen = open ?? inner;
  return (
    <OpenContext value={isOpen}>
      <DialogPrimitive.Root
        open={isOpen}
        onOpenChange={(next) => {
          setInner(next);
          onOpenChange?.(next);
        }}
        {...props}
      />
    </OpenContext>
  );
}

const DialogTrigger = DialogPrimitive.Trigger;
const DialogClose = DialogPrimitive.Close;

function DialogContent({ className, children, ...props }: ComponentProps<typeof DialogPrimitive.Content>) {
  const open = use(OpenContext);
  return (
    <AnimatePresence>
      {open ? (
        <DialogPrimitive.Portal forceMount>
          <DialogPrimitive.Overlay asChild forceMount>
            <motion.div
              className="fixed inset-0 z-50 bg-scrim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.14 }}
            />
          </DialogPrimitive.Overlay>
          <DialogPrimitive.Content asChild forceMount {...props}>
            <motion.div
              className={cn(
                "glass fixed inset-x-4 top-[12vh] z-50 mx-auto max-w-lg rounded-lg border border-border-strong text-popover-foreground",
                className,
              )}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
            >
              {children}
            </motion.div>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      ) : null}
    </AnimatePresence>
  );
}

function DialogHeader({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-1.5 p-5 pb-0", className)} {...props} />;
}

function DialogTitle({ className, ...props }: ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title className={cn("font-heading text-2xl", className)} {...props} />;
}

function DialogDescription({ className, ...props }: ComponentProps<typeof DialogPrimitive.Description>) {
  return <DialogPrimitive.Description className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export { Dialog, DialogTrigger, DialogClose, DialogContent, DialogHeader, DialogTitle, DialogDescription };
