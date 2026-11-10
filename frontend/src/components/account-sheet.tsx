import { LogOut, Search } from "lucide-react";
import type { RefObject } from "react";
import { useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import type { EventsStatus } from "@/events/use-events";
import { GlassSheet } from "@/features/chat/glass-sheet";
import { LiveStatus } from "./live-status";
import { usePalette } from "./palette-context";
import { ThemeToggle } from "./theme-toggle";

/** The sidebar's footer for phones: workspace, connection, theme, search and sign out, in a bottom sheet. */
export function AccountSheet({
  open,
  onOpenChange,
  liveStatus,
  returnFocusTo,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  liveStatus: EventsStatus;
  returnFocusTo: RefObject<HTMLElement | null>;
}) {
  const { state, actions } = useAuth();
  const { setOpen } = usePalette();
  if (state.status !== "authenticated") return null;
  return (
    <GlassSheet
      open={open}
      onOpenChange={onOpenChange}
      placement="bottom"
      title="Account"
      description="Workspace, connection, theme and sign out."
      returnFocusTo={returnFocusTo}
    >
      <div className="flex flex-col gap-4">
        <div className="space-y-1">
          <p className="text-sm">{state.user.email}</p>
          <p className="text-meta text-muted-foreground">{state.workspace.slug}</p>
          <LiveStatus status={liveStatus} />
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button
            variant="secondary"
            onClick={() => {
              onOpenChange(false);
              setOpen(true);
            }}
          >
            <Search aria-hidden />
            Search
          </Button>
          <Button variant="secondary" onClick={() => void actions.signOut()}>
            <LogOut aria-hidden />
            Sign out
          </Button>
        </div>
      </div>
    </GlassSheet>
  );
}
