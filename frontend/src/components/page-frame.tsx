import type { ReactNode, Ref } from "react";
import { cn } from "@/lib/utils";

/**
 * The frame every page shares. The page fills the shell cell; a floating glass header sits one gutter in from the
 * edges; the content scrolls underneath it and is blurred through it.
 *
 * `scroll` (default): one content column (--page-max) that scrolls, the header stays.
 * `fill`: the page lays out its own scroll areas inside the padded region (Inbox).
 * `bleed`: the page fills the whole cell under the header and pads its own scroller (Chat), so messages pass beneath
 * the header and the composer and are blurred through them.
 *
 * The h1 is the page title (Instrument Serif at about 28px) unless `plainTitle` is set (the chat's conversation
 * title is small sans text).
 */
export function PageFrame({
  title,
  plainTitle = false,
  actions,
  headingRef,
  mode = "scroll",
  children,
}: {
  title: ReactNode;
  plainTitle?: boolean;
  actions?: ReactNode;
  headingRef?: Ref<HTMLHeadingElement>;
  mode?: "scroll" | "fill" | "bleed";
  children: ReactNode;
}) {
  return (
    <div className="relative h-full min-h-0">
      <header className="glass-thick absolute inset-x-(--gutter) top-(--gutter) z-20 flex h-(--header-h) items-center justify-between gap-3 rounded-full px-5">
        <h1
          ref={headingRef}
          tabIndex={-1}
          className={cn("min-w-0 truncate outline-none", plainTitle ? "text-label" : "font-heading")}
        >
          {title}
        </h1>
        {actions ? <div className="flex shrink-0 items-center gap-1">{actions}</div> : null}
      </header>
      {mode === "bleed" ? (
        <div className="absolute inset-0">{children}</div>
      ) : mode === "scroll" ? (
        <div className="scroll-area absolute inset-0 pt-[calc(var(--gutter)*2+var(--header-h)+0.5rem)] pb-[calc(var(--page-bottom)+var(--gutter))]">
          <div className="mx-auto flex w-full max-w-(--page-max) flex-col gap-6 px-4 sm:px-6">{children}</div>
        </div>
      ) : (
        <div className="absolute inset-0 pt-[calc(var(--gutter)*2+var(--header-h))] pb-(--page-bottom)">{children}</div>
      )}
    </div>
  );
}
