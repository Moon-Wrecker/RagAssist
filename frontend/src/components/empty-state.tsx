import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** A quiet, centred line (and at most one action) for a list or table with nothing to show. */
export function EmptyState({ title, hint, children, className }: { title: string; hint?: string; children?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-1.5 px-6 py-14 text-center", className)}>
      <p className="font-medium">{title}</p>
      {hint ? <p className="max-w-xs text-sm text-muted-foreground">{hint}</p> : null}
      {children ? <div className="mt-3 flex gap-2">{children}</div> : null}
    </div>
  );
}

/** The error twin of EmptyState: what failed, and one way to try again. It is announced to screen readers. */
export function ErrorState({ what, onRetry, className }: { what: string; onRetry: () => void; className?: string }) {
  return (
    <div role="alert" className={cn("flex flex-col items-center justify-center gap-3 px-6 py-14 text-center", className)}>
      <p className="font-medium">{`${what} could not be loaded.`}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}
