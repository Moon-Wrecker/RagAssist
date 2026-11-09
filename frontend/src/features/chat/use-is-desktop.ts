import { useSyncExternalStore } from "react";

const DESKTOP = "(min-width: 1024px)";

function subscribe(onChange: () => void): () => void {
  if (typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia(DESKTOP);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** True at laptop width (1024px) and above. False where `matchMedia` is missing, so the phone layout is the safe default. */
export function useIsDesktop(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => typeof window.matchMedia === "function" && window.matchMedia(DESKTOP).matches,
    () => false,
  );
}
