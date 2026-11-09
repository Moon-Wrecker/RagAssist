import { useQuery } from "@tanstack/react-query";
import type { RefObject } from "react";
import { ApiError } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { getPassage, passageKey } from "./api";
import { GlassSheet } from "./glass-sheet";
import { sourceLocation } from "./source-location";
import { useIsDesktop } from "./use-is-desktop";
import type { Citation } from "./types";

export interface OpenSource {
  citation: Citation;
  number: number;
}

/**
 * The passage behind a citation, loaded from `GET /v1/chunks/{id}`: a side panel on desktop, a bottom sheet on
 * phones. Passage text is document text and therefore untrusted: it is shown as plain text, never parsed.
 */
export function CitationPanel({
  source,
  onClose,
  returnFocusTo,
}: {
  source: OpenSource | null;
  onClose: () => void;
  returnFocusTo: RefObject<HTMLElement | null>;
}) {
  const desktop = useIsDesktop();
  return (
    <GlassSheet
      open={source !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      placement={desktop ? "right" : "bottom"}
      modal={!desktop}
      title={source ? `Source ${source.number}` : "Source"}
      description="The exact passage this part of the answer is based on."
      returnFocusTo={returnFocusTo}
    >
      {source ? <PassageBody key={source.citation.chunkId} source={source} /> : null}
    </GlassSheet>
  );
}

function PassageBody({ source }: { source: OpenSource }) {
  const { citation } = source;
  const query = useQuery({
    queryKey: passageKey(citation.chunkId),
    queryFn: () => getPassage(citation.chunkId),
    staleTime: 5 * 60_000,
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
  });

  if (query.isPending) {
    return (
      <p role="status" className="font-mono text-sm text-muted-foreground">
        Loading the passage
      </p>
    );
  }
  if (query.isError) {
    const gone = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div role="alert" className="space-y-3 text-sm">
        <p>
          {gone
            ? "This passage is no longer available. The document may have been removed or re-indexed."
            : "The passage could not be loaded."}
        </p>
        {gone ? null : (
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            Try again
          </Button>
        )}
        <p className="font-mono text-xs text-muted-foreground">{citation.title || citation.chunkId}</p>
      </div>
    );
  }

  const passage = query.data;
  const where = sourceLocation({ headingPath: passage.heading_path, page: passage.page });
  return (
    <article className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-base font-semibold break-words">{passage.document_title || citation.title || "Untitled document"}</h2>
        {passage.title && passage.title !== passage.document_title ? (
          <p className="text-sm text-muted-foreground break-words">{passage.title}</p>
        ) : null}
        {where || passage.is_global ? (
          <p className="font-mono text-xs text-muted-foreground break-words">
            {[where, passage.is_global ? "shared knowledge" : ""].filter((part) => part !== "").join("  ·  ")}
          </p>
        ) : null}
      </header>
      <blockquote className="border-l-2 border-border-strong pl-4 text-[0.9375rem] leading-relaxed whitespace-pre-wrap break-words">
        {passage.text}
      </blockquote>
    </article>
  );
}
