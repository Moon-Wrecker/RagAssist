import { CircleUser } from "lucide-react";
import { useRef, useState } from "react";
import { routesFor } from "@/app/access";
import { useAuth } from "@/auth/auth-context";
import type { EventsStatus } from "@/events/use-events";
import { AccountSheet } from "./account-sheet";
import { NavEntry } from "./nav";
import { cn } from "@/lib/utils";

/** Phones: a floating glass tab bar one gutter above the bottom edge. The last tab opens the account sheet. */
export function BottomTabs({ liveStatus }: { liveStatus: EventsStatus }) {
  const { state } = useAuth();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  if (state.status !== "authenticated") return null;
  const routes = routesFor(state.user.role);

  return (
    <>
      <nav
        aria-label="Main"
        className="glass-regular fixed inset-x-(--gutter) bottom-(--gutter) z-30 flex h-14 items-center gap-1 rounded-full p-1 md:hidden"
      >
        {routes.map((route) => (
          <NavEntry key={route.path} route={route} orientation="tab" thumbId="tabbar-thumb" />
        ))}
        <button
          ref={trigger}
          type="button"
          onClick={() => setOpen(true)}
          className={cn("press relative flex h-12 flex-1 flex-col items-center justify-center gap-0.5 rounded-full text-[0.6875rem] text-label text-muted-foreground hover:text-foreground")}
        >
          <CircleUser aria-hidden className="size-[1.125rem]" strokeWidth={1.75} />
          Account
        </button>
      </nav>
      <AccountSheet open={open} onOpenChange={setOpen} liveStatus={liveStatus} returnFocusTo={trigger} />
    </>
  );
}
