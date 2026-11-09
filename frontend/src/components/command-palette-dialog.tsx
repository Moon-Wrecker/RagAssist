import { CornerDownLeft, LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router";
import { routesFor } from "@/app/access";
import { useAuth } from "@/auth/auth-context";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useTheme } from "@/theme/theme-context";
import { usePalette } from "./palette-context";

/** Cmd/Ctrl K: jump to a page, change the theme, sign out. History search joins it with the chat slice. */
export default function CommandPaletteDialog() {
  const { open, setOpen } = usePalette();
  const { state, actions: auth } = useAuth();
  const { actions: theme } = useTheme();
  const navigate = useNavigate();
  const role = state.status === "authenticated" ? state.user.role : null;
  const routes = useMemo(() => (role ? routesFor(role) : []), [role]);

  function run(action: () => void | Promise<void>) {
    setOpen(false);
    void action();
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="top-[10vh] p-0">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <DialogDescription className="sr-only">Search for a page or an action, then press Enter.</DialogDescription>
        <Command label="Command palette">
          <CommandInput placeholder="Search pages and actions" />
          <CommandList>
            <CommandEmpty>Nothing matches. Try a page name such as Chat or Team.</CommandEmpty>
            {routes.length > 0 ? (
              <CommandGroup heading="Go to">
                {routes.map((route) => (
                  <CommandItem
                    key={route.path}
                    value={`go ${route.label}`}
                    onSelect={() => run(() => navigate(route.path))}
                  >
                    <CornerDownLeft aria-hidden />
                    {route.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            ) : null}
            <CommandGroup heading="Theme">
              <CommandItem value="theme light" onSelect={() => run(() => theme.setPreference("light"))}>
                <Sun aria-hidden />
                Light
              </CommandItem>
              <CommandItem value="theme dark" onSelect={() => run(() => theme.setPreference("dark"))}>
                <Moon aria-hidden />
                Dark
              </CommandItem>
              <CommandItem value="theme system" onSelect={() => run(() => theme.setPreference("system"))}>
                <Monitor aria-hidden />
                Follow the system
              </CommandItem>
            </CommandGroup>
            {role ? (
              <CommandGroup heading="Account">
                <CommandItem value="sign out" onSelect={() => run(auth.signOut)}>
                  <LogOut aria-hidden />
                  Sign out
                </CommandItem>
              </CommandGroup>
            ) : null}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
