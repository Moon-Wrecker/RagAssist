import { motion } from "motion/react";
import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router";
import { trackReadingColumn } from "@/background";
import { useEvents } from "@/events/use-events";
import { pageEnter } from "@/lib/motion";
import { BottomTabs } from "./bottom-tabs";
import { PaletteProvider } from "./command-palette";
import { Sidebar } from "./sidebar";

/**
 * The app shell is a grid fixed at 100dvh: the floating glass sidebar on the left (a tab bar on phones) and the
 * page cell beside it. The document never scrolls; every page owns its scrollers (PageFrame, Chat, Inbox).
 */
export function AppShell() {
  // The shell only mounts for a signed-in user, so the live stream runs exactly while someone is signed in.
  const liveStatus = useEvents(true);
  const { pathname } = useLocation();
  const cell = useRef<HTMLElement>(null);

  // Tell the liquid background where the reading column is so its dark scrim sits under it.
  useEffect(() => (cell.current ? trackReadingColumn(cell.current) : undefined), []);

  return (
    <PaletteProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-background focus:px-4 focus:py-2"
      >
        Skip to content
      </a>
      <div className="grid h-dvh grid-cols-1 overflow-hidden max-md:[--page-bottom:calc(3.5rem+var(--gutter)*2)] md:grid-cols-[auto_minmax(0,1fr)]">
        <Sidebar liveStatus={liveStatus} />
        <main ref={cell} id="main" tabIndex={-1} className="relative min-h-0 min-w-0 outline-none">
          <motion.div key={pathname} className="h-full" {...pageEnter}>
            <Outlet />
          </motion.div>
        </main>
      </div>
      <BottomTabs liveStatus={liveStatus} />
    </PaletteProvider>
  );
}
