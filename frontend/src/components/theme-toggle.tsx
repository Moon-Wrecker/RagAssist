import { Monitor, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { nextPreference, useTheme, type ThemePreference } from "@/theme/theme-context";

const LABEL: Record<ThemePreference, string> = { system: "System", light: "Light", dark: "Dark" };
const ICON = { system: Monitor, light: Sun, dark: Moon } as const;

/** One button that steps System, Light, Dark. The accessible name says what is on and what a press does. */
export function ThemeToggle() {
  const {
    state: { preference },
    actions: { cycle },
  } = useTheme();
  const Icon = ICON[preference];
  const next = LABEL[nextPreference(preference)];
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={cycle}
      aria-label={`Theme: ${LABEL[preference]}. Switch to ${next}.`}
      title={`Theme: ${LABEL[preference]}`}
    >
      <Icon aria-hidden />
    </Button>
  );
}
