import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { acceptLink as acceptLinkRequest, login, logout, restoreSession } from "@/api/auth";
import { onSessionLost } from "@/api/http";
import type { AcceptRequest, LoginRequest, Session } from "@/api/types";
import { AuthContext, type AuthContextValue, type AuthState } from "./auth-context";

function authenticated(session: Session): AuthState {
  return { status: "authenticated", user: session.user, workspace: session.workspace };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  // Restore the session from the httpOnly refresh cookie after a reload (the access token is memory only).
  // StrictMode runs this twice in development; refreshSession() is single-flight so only one request is sent.
  useEffect(() => {
    let cancelled = false;
    restoreSession().then(
      (session) => {
        if (!cancelled) setState(session ? authenticated(session) : { status: "anonymous" });
      },
      () => {
        if (!cancelled) setState({ status: "unreachable" });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  // A refresh that the server refuses mid-session means the session is over: drop cached data, show sign-in.
  useEffect(
    () =>
      onSessionLost(() => {
        queryClient.clear();
        setState({ status: "anonymous" });
      }),
    [queryClient],
  );

  const signIn = useCallback(async (request: LoginRequest) => {
    setState(authenticated(await login(request)));
  }, []);

  const acceptLink = useCallback(async (request: AcceptRequest) => {
    setState(authenticated(await acceptLinkRequest(request)));
  }, []);

  const signOut = useCallback(async () => {
    try {
      await logout();
    } finally {
      queryClient.clear();
      setState({ status: "anonymous" });
    }
  }, [queryClient]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ state, actions: { signIn, acceptLink, signOut, retry } }),
    [state, signIn, acceptLink, signOut, retry],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
