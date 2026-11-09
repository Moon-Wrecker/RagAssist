import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** The page-level glass container (level 1). Do not place another glass surface inside it. */
export function Panel({ className, ...props }: ComponentProps<"section">) {
  return <section className={cn("glass-1 rounded-lg p-6 sm:p-8", className)} {...props} />;
}
