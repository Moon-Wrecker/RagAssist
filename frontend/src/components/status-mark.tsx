import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type StatusEmphasis = "strong" | "normal" | "muted" | "alert";

/**
 * A status as a small mono label with a glyph (no pill, no border), by shape, weight and pattern plus its word, never colour: the icon differs in shape (filled dot, dashed
 * ring, check, cross), `strong` is bold, `muted` is dimmed, and `alert` adds a dashed underline. The word is always
 * present, so the icon is decoration for assistive technology.
 */
export function StatusMark({
  icon: Icon,
  label,
  emphasis = "normal",
  className,
}: {
  icon: LucideIcon;
  label: string;
  emphasis?: StatusEmphasis;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-meta",
        emphasis === "strong" && "font-medium text-foreground",
        emphasis === "normal" && "text-foreground",
        emphasis === "muted" && "text-muted-foreground",
        emphasis === "alert" && "font-medium text-foreground underline decoration-dashed underline-offset-4",
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5 shrink-0" strokeWidth={emphasis === "strong" || emphasis === "alert" ? 2.4 : 1.75} />
      {label}
    </span>
  );
}
