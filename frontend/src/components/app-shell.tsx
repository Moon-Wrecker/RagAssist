import { Outlet } from "react-router";
import { useEvents } from "@/events/use-events";
import { PaletteProvider } from "./command-palette";
import { TopBar } from "./top-bar";

/** Top bar over a full-width page. The skip link is the first tab stop. */
export function AppShell() {
  // The shell only mounts for a signed-in user, so the live stream runs exactly while someone is signed in.
  const liveStatus = useEvents(true);
  return (
    <PaletteProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <TopBar liveStatus={liveStatus} />
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[90rem] px-4 pt-10 pb-16 sm:px-6 sm:pt-14">
        <Outlet />
      </main>
    </PaletteProvider>
  );
}
