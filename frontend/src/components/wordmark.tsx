import { cn } from "@/lib/utils";

/** The product name set in the interface face; the serif is kept for page titles. */
export function Wordmark({ className }: { className?: string }) {
  return <span className={cn("text-[0.9375rem] font-semibold tracking-tight", className)}>RagAssist</span>;
}
