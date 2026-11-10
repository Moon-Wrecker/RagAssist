import { startCursor } from "@/lib/cursor";
import { startPointerLight } from "@/lib/pointer-light";
import { enableLens } from "./lens";
import { startLiquid, type LiquidHandle } from "./liquid";

let liquid: LiquidHandle | null = null;

/** Starts the non-React layers once: the liquid canvas, the glass light that follows the pointer, the lens, the cursor. */
export function startBackdrop(): void {
  liquid = startLiquid();
  startPointerLight();
  enableLens();
  startCursor();
}

/** Tell the background where the reading column is, so the dark scrim sits under it. Returns a stop function. */
export function trackReadingColumn(element: HTMLElement): () => void {
  const report = () => {
    const rect = element.getBoundingClientRect();
    const width = window.innerWidth;
    if (width === 0 || rect.width === 0) return;
    liquid?.setColumn((rect.left + rect.width / 2) / width, rect.width / 2 / width);
  };
  const observer = new ResizeObserver(report);
  observer.observe(element);
  window.addEventListener("resize", report, { passive: true });
  report();
  return () => {
    observer.disconnect();
    window.removeEventListener("resize", report);
  };
}
