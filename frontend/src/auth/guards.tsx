import { Link, Navigate, Outlet, useLocation } from "react-router";
import { Button } from "@/components/ui/button";
import { StatusPage } from "@/components/status-page";
import type { Role } from "@/api/types";
import { landingPath } from "@/app/access";
import { useAuth } from "./auth-context";

/** Where the guard bounced the visitor from, so sign-in can send them back. */
export interface FromState {
  from?: { pathname: string };
}

function Restoring() {
  return <StatusPage title="Restoring your session" body="One moment." live />;
}

/** Anything behind this route needs a signed-in user. */
export function RequireAuth() {
  const { state, actions } = useAuth();
  const location = useLocation();

  switch (state.status) {
    case "loading":
      return <Restoring />;
    case "unreachable":
      return (
        <StatusPage
          title="Can't reach the server"
          body="Check your connection, then try again. You are not signed out."
          live
        >
          <Button onClick={actions.retry}>Try again</Button>
        </StatusPage>
      );
    case "anonymous":
      return <Navigate to="/sign-in" replace state={{ from: { pathname: location.pathname } } satisfies FromState} />;
    case "authenticated":
      return <Outlet />;
  }
}

/** Nested inside RequireAuth: only the listed roles get through; everyone else sees a plain explanation. */
export function RequireRole({ roles }: { roles: readonly Role[] }) {
  const { state } = useAuth();
  if (state.status !== "authenticated") return <Restoring />;
  if (!roles.includes(state.user.role)) {
    return (
      <StatusPage title="This page is not available to your role" body="Ask a workspace admin if you need access.">
        <Button asChild variant="outline">
          <Link to="/">Back to chat</Link>
        </Button>
      </StatusPage>
    );
  }
  return <Outlet />;
}

/** Sign-in and invite screens: a signed-in visitor is sent on to the app instead. */
export function PublicOnly() {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status === "loading") return <Restoring />;
  if (state.status === "authenticated") {
    const from = (location.state as FromState | null)?.from?.pathname;
    return <Navigate to={landingPath(state.user.role, from)} replace />;
  }
  return <Outlet />;
}
