import { LogOut, Search } from "lucide-react";
import { NavLink } from "react-router";
import { routesFor } from "@/app/access";
import { useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { shortcutLabel, usePalette } from "./palette-context";
import { ThemeToggle } from "./theme-toggle";
import { Wordmark } from "./wordmark";

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    "inline-flex h-10 items-center border-b-2 border-transparent px-1 text-sm text-muted-foreground transition-colors hover:text-foreground",
    isActive && "border-foreground font-medium text-foreground",
  );
}

/** Glass top bar: wordmark, role-aware navigation, search, theme, sign out. Navigation wraps below on phones. */
export function TopBar() {
  const { state, actions } = useAuth();
  const { setOpen } = usePalette();
  if (state.status !== "authenticated") return null;
  const routes = routesFor(state.user.role);

  return (
    <header className="glass sticky top-0 z-40 border-b">
      <div className="mx-auto flex w-full max-w-[90rem] flex-wrap items-center gap-x-6 px-4 sm:px-6 md:flex-nowrap">
        <NavLink to="/" className="flex h-14 items-center rounded-md" aria-label="RagAssist home">
          <Wordmark />
        </NavLink>
        <nav
          aria-label="Main"
          className="order-3 flex w-full items-end gap-5 overflow-x-auto md:order-none md:w-auto"
        >
          {routes.map((route) => (
            <NavLink key={route.path} to={route.path} end={route.path === "/"} className={navClass}>
              {route.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex h-14 items-center gap-1">
          <span className="mr-2 hidden font-mono text-xs text-muted-foreground lg:inline">{state.workspace.slug}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setOpen(true)}
            aria-label="Open the command palette"
            className="px-2.5"
          >
            <Search aria-hidden />
            <kbd className="hidden rounded-sm border px-1.5 py-0.5 font-mono text-[0.6875rem] font-normal text-muted-foreground sm:inline">
              {shortcutLabel()}
            </kbd>
          </Button>
          <ThemeToggle />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => void actions.signOut()}
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut aria-hidden />
          </Button>
        </div>
      </div>
    </header>
  );
}
