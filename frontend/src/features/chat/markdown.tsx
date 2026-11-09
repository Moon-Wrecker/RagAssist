import { Children, Fragment, createElement, useMemo, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import type { Citation } from "./types";

/**
 * Renders model text. Model and document text is untrusted, so:
 * - no raw HTML (there is no `rehype-raw`; HTML in the text is shown as text or dropped, never parsed),
 * - `rehype-sanitize` with its default schema (GitHub's allow-list): no scripts, no event handlers, and links
 *   only with http, https, mailto, irc, ircs or xmpp (so `javascript:` is removed),
 * - no images (a remote image is a request the author of the text controls),
 * - links open in a new tab with `noopener noreferrer`.
 * `[n]` markers become buttons for the n-th citation; a marker without a matching citation stays plain text.
 */
const MARKER = /\[(\d{1,3})\]/g;

export type OpenCitation = (citation: Citation, index: number, trigger: HTMLElement) => void;

function withMarkers(children: ReactNode, citations: readonly Citation[], open: OpenCitation): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child !== "string") return child;
    const parts: ReactNode[] = [];
    let last = 0;
    for (const match of child.matchAll(MARKER)) {
      const number = Number(match[1]);
      const citation = citations[number - 1];
      if (!citation) continue;
      if (match.index > last) parts.push(child.slice(last, match.index));
      parts.push(<CitationMarker key={`${match.index}-${number}`} number={number} citation={citation} onOpen={open} />);
      last = match.index + match[0].length;
    }
    if (parts.length === 0) return child;
    if (last < child.length) parts.push(child.slice(last));
    return <Fragment>{parts}</Fragment>;
  });
}

function CitationMarker({
  number,
  citation,
  onOpen,
}: {
  number: number;
  citation: Citation;
  onOpen: OpenCitation;
}) {
  const label = citation.title ? `Source ${number}: ${citation.title}` : `Source ${number}`;
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(event) => onOpen(citation, number, event.currentTarget)}
      className="mx-0.5 inline-flex min-h-6 min-w-6 items-center justify-center rounded-sm border border-border-strong px-1 align-baseline font-mono text-[0.6875rem] leading-none text-foreground transition-colors hover:bg-accent"
    >
      {number}
    </button>
  );
}

/** react-markdown passes the hast `node` to every component; it must not reach the DOM. */
function omitNode<T extends object>(props: T): Omit<T, "node"> {
  const copy = { ...(props as Record<string, unknown>) };
  delete copy.node;
  return copy as Omit<T, "node">;
}

type ElementProps = { node?: unknown; children?: ReactNode; className?: string };

/** The component map for one message. Text inside the elements that hold prose gets citation markers. */
function buildComponents(citations: readonly Citation[], open: OpenCitation): Components {
  const mark = (children: ReactNode) => withMarkers(children, citations, open);
  /** An element with fixed classes; `markers` says whether its text may contain citation markers. */
  const styled = (tag: string, className: string, markers: boolean) =>
    function StyledElement({ children, className: extra, ...props }: ElementProps) {
      return createElement(tag, { ...omitNode(props), className: cn(className, extra) }, markers ? mark(children) : children);
    };
  const heading = (tag: string) => styled(tag, "mt-6 mb-2 text-base font-semibold first:mt-0", true);

  return {
    p: styled("p", "my-3 first:mt-0 last:mb-0", true),
    li: styled("li", "my-1", true),
    td: styled("td", "border-b px-3 py-1.5 align-top", true),
    th: styled("th", "border-b border-border-strong px-3 py-1.5 text-left font-medium", true),
    strong: styled("strong", "font-semibold", true),
    em: styled("em", "italic", true),
    h1: heading("h1"),
    h2: heading("h2"),
    h3: heading("h3"),
    h4: heading("h4"),
    h5: heading("h5"),
    h6: heading("h6"),
    ul: styled("ul", "my-3 list-disc pl-6", false),
    ol: styled("ol", "my-3 list-decimal pl-6", false),
    blockquote: styled("blockquote", "my-3 border-l-2 border-border-strong pl-4 text-muted-foreground", false),
    hr: styled("hr", "my-6", false),
    table: ({ children, ...props }: ElementProps) => (
      <div className="my-3 overflow-x-auto">
        <table {...omitNode(props)} className="w-full border-collapse text-sm">
          {children}
        </table>
      </div>
    ),
    pre: styled("pre", "my-3 overflow-x-auto rounded-md border bg-accent p-3 font-mono text-[0.8125rem] leading-relaxed", false),
    code: ({ className, children, ...props }: ElementProps) => (
      <code {...omitNode(props)} className={cn("font-mono text-[0.875em]", !className && "rounded-sm bg-accent px-1 py-0.5", className)}>
        {children}
      </code>
    ),
    a: ({ href, children, ...props }: ElementProps & { href?: string }) => (
      <a {...omitNode(props)} href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 hover:decoration-2">
        {mark(children)}
      </a>
    ),
  };
}

export function Markdown({
  text,
  citations,
  onOpenCitation,
  className,
}: {
  text: string;
  citations: readonly Citation[];
  onOpenCitation: OpenCitation;
  className?: string;
}) {
  const components = useMemo(() => buildComponents(citations, onOpenCitation), [citations, onOpenCitation]);
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={components}
        disallowedElements={["img"]}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
