import type { Role } from "@/api/types";

/** One table drives both the navigation and the route guards, so they cannot disagree. */
export interface AppRoute {
  path: string;
  label: string;
  roles: readonly Role[];
}

export const HOME_PATH = "/";

export const APP_ROUTES: readonly AppRoute[] = [
  { path: "/", label: "Chat", roles: ["user", "agent", "admin"] },
  { path: "/inbox", label: "Inbox", roles: ["agent", "admin"] },
  { path: "/knowledge", label: "Knowledge", roles: ["admin"] },
  { path: "/team", label: "Team", roles: ["admin"] },
];

export function routesFor(role: Role): AppRoute[] {
  return APP_ROUTES.filter((route) => route.roles.includes(role));
}

export function canAccess(role: Role, path: string): boolean {
  const route = APP_ROUTES.find((candidate) => candidate.path === path);
  return route ? route.roles.includes(role) : false;
}

/** Where to send someone after sign-in: the page they asked for if their role allows it, else the home page. */
export function landingPath(role: Role, requested: string | null | undefined): string {
  if (requested && canAccess(role, requested)) return requested;
  return HOME_PATH;
}
