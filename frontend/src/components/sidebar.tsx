import { LogOut, PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";
import { routesFor } from "@/app/access";
import { useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import type { EventsStatus } from "@/events/use-events";
import { CONVERSATION_PARAM } from "@/features/chat/use-chat";
import { cn } from "@/lib/utils";
import { HistoryList } from "./history-list";
import { LiveStatus } from "./live-status";
import { NavEntry } from "./nav";
import { shortcutLabel, usePalette } from "./palette-context";
import { ThemeToggle } from "./theme-toggle";
import { Wordmark } from "./wordmark";

const STORAGE_KEY = "ragassist-sidebar";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "collapsed";
  } catch {
    return false;
  }
}

/**
 * The floating glass sidebar: it sits one gutter in from the window edges with large rounded corners. Logo,
 * navigation with a sliding glass thumb, the chat history while on Chat, and workspace, connection, theme and
 * sign-out at the bottom. Collapses to icons; the choice is remembered.
 */
export function Sidebar({ liveStatus }: { liveStatus: EventsStatus }) {
  const { state, actions } = useAuth();
  const { setOpen } = usePalette();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [collapsed, setCollapsed] = useState(readCollapsed);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? "collapsed" : "open");
    } catch {
      // Not remembered; still applied for this visit.
    }
  }, [collapsed]);

  if (state.status !== "authenticated") return null;
  const routes = routesFor(state.user.role);
  const onChat = pathname === "/";

  return (
    <aside
      aria-label="Sidebar"
      className="hidden p-(--gutter) md:block"
    >
      <div
        className={cn(
          "glass-regular flex h-full flex-col gap-3 rounded-(--r-bar) p-3",
          collapsed ? "w-(--sidebar-w-collapsed)" : "w-(--sidebar-w)",
        )}
        style={{ ["--r-outer" as string]: "1.75rem", ["--pad" as string]: "0.75rem" }}
      >
        <div className={cn("flex h-10 items-center", collapsed ? "justify-center" : "justify-between pl-2")}>
          {collapsed ? null : <Wordmark />}
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
            aria-expanded={!collapsed}
          >
            {collapsed ? <PanelLeftOpen aria-hidden /> : <PanelLeftClose aria-hidden />}
          </Button>
        </div>

        <nav aria-label="Main" className="flex flex-col gap-1">
          {routes.map((route) => (
            <NavEntry key={route.path} route={route} orientation="row" collapsed={collapsed} thumbId="sidebar-thumb" />
          ))}
        </nav>

        {onChat && !collapsed ? (
          <div className="flex min-h-0 flex-1 flex-col gap-1.5 border-t pt-3">
            <p className="text-meta px-2 text-muted-foreground">History</p>
            <HistoryList
              activeId={params.get(CONVERSATION_PARAM)}
              onSelect={(id) => navigate({ pathname: "/", search: `?${CONVERSATION_PARAM}=${encodeURIComponent(id)}` })}
              onNew={() => navigate({ pathname: "/", search: "" })}
            />
          </div>
        ) : (
          <div className="flex-1" />
        )}

        <div className={cn("flex flex-col gap-1 border-t pt-3", collapsed && "items-center")}>
          <Button
            variant="ghost"
            size={collapsed ? "icon" : "default"}
            onClick={() => setOpen(true)}
            aria-label="Open the command palette"
            className={cn(!collapsed && "justify-start px-3.5")}
          >
            <Search aria-hidden />
            {collapsed ? null : (
              <>
                <span className="flex-1 text-left">Search</span>
                <kbd className="text-meta text-muted-foreground">{shortcutLabel()}</kbd>
              </>
            )}
          </Button>
          <div className={cn("flex items-center gap-1", collapsed ? "flex-col" : "justify-between pl-3.5")}>
            {collapsed ? null : (
              <span className="text-meta min-w-0 truncate text-muted-foreground" title="Workspace">
                {state.workspace.slug}
              </span>
            )}
            <div className={cn("flex items-center", collapsed && "flex-col")}>
              <ThemeToggle />
              <Button variant="ghost" size="icon" onClick={() => void actions.signOut()} aria-label="Sign out" title="Sign out">
                <LogOut aria-hidden />
              </Button>
            </div>
          </div>
          <LiveStatus status={liveStatus} className={cn(collapsed ? "justify-center" : "pl-3.5")} />
        </div>
      </div>
    </aside>
  );
}
