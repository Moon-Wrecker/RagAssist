import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { PaletteContext, type PaletteContextValue } from "./palette-context";

// The palette (cmdk, dialog, motion) loads the first time it is opened, keeping it out of the first paint.
const CommandPaletteDialog = lazy(() => import("./command-palette-dialog"));

export function PaletteProvider({ children }: { children: ReactNode }) {
  const [open, setOpenState] = useState(false);
  const [everOpened, setEverOpened] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setEverOpened(true);
        setOpenState((current) => !current);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const setOpen = useCallback((next: boolean) => {
    if (next) setEverOpened(true);
    setOpenState(next);
  }, []);

  const value = useMemo<PaletteContextValue>(() => ({ open, setOpen }), [open, setOpen]);
  return (
    <PaletteContext value={value}>
      {children}
      {everOpened ? (
        <Suspense fallback={null}>
          <CommandPaletteDialog />
        </Suspense>
      ) : null}
    </PaletteContext>
  );
}

