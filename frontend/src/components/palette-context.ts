import { createContext, use } from "react";

export interface PaletteContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

export const PaletteContext = createContext<PaletteContextValue | null>(null);

export function usePalette(): PaletteContextValue {
  const value = use(PaletteContext);
  if (!value) throw new Error("usePalette must be used inside PaletteProvider");
  return value;
}

/** The Command key symbol on Apple platforms, "Ctrl K" elsewhere. */
export function shortcutLabel(): string {
  const apple = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);
  return apple ? "⌘K" : "Ctrl K";
}
