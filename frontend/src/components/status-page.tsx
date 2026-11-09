import type { ReactNode } from "react";
import { Panel } from "./panel";

/** A plain full-page message: loading, unreachable, no access. Left aligned, serif title, one next step. */
export function StatusPage({
  title,
  body,
  live = false,
  children,
}: {
  title: string;
  body: string;
  /** Announce changes to screen readers (loading and error states). */
  live?: boolean;
  children?: ReactNode;
}) {
  return (
    <main className="mx-auto w-full max-w-2xl px-4 pt-[12vh] sm:px-6">
      <Panel>
        <div aria-live={live ? "polite" : undefined}>
          <h1 className="font-heading text-4xl sm:text-5xl">{title}</h1>
          <p className="mt-3 max-w-prose text-muted-foreground">{body}</p>
        </div>
        {children ? <div className="mt-6 flex gap-3">{children}</div> : null}
      </Panel>
    </main>
  );
}
