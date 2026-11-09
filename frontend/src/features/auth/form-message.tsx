import { AnimatePresence, motion } from "motion/react";

/**
 * A live region for form status. It stays mounted (so screen readers register it before content arrives) and the
 * message fades in. A leading glyph and dashed rule mark an error without colour.
 */
export function FormMessage({ id, message }: { id: string; message: string | null }) {
  return (
    <div id={id} aria-live="polite" className="min-h-0">
      <AnimatePresence initial={false}>
        {message ? (
          <motion.p
            key={message}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="border-l-2 border-dashed border-foreground py-1 pl-3 text-sm"
          >
            <span aria-hidden className="mr-2 font-mono font-medium">
              !
            </span>
            {message}
          </motion.p>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
