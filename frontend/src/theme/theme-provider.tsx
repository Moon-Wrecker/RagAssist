import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  nextPreference,
  resolveTheme,
  ThemeContext,
  type ThemeContextValue,
  type ThemePreference,
} from "./theme-context";

const STORAGE_KEY = "ragassist-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function readStoredPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Storage can be blocked; the theme then simply follows the system.
  }
  return "system";
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredPreference);
  const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(DARK_QUERY);
    const onChange = () => setSystemDark(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const resolved = resolveTheme(preference, systemDark);

  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
  }, [resolved]);

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    try {
      if (next === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not persisted; still applied for this visit.
    }
  }, []);

  const cycle = useCallback(() => setPreference(nextPreference(preference)), [preference, setPreference]);

  const value = useMemo<ThemeContextValue>(
    () => ({ state: { preference, resolved }, actions: { setPreference, cycle } }),
    [preference, resolved, setPreference, cycle],
  );

  return <ThemeContext value={value}>{children}</ThemeContext>;
}
