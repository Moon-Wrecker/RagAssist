import { createContext, use } from "react";
import type { AcceptRequest, LoginRequest, User, Workspace } from "@/api/types";

export type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  /** The server could not be reached while restoring the session; the session itself may still be valid. */
  | { status: "unreachable" }
  | { status: "authenticated"; user: User; workspace: Workspace };

export interface AuthContextValue {
  state: AuthState;
  actions: {
    signIn: (request: LoginRequest) => Promise<void>;
    acceptLink: (request: AcceptRequest) => Promise<void>;
    signOut: () => Promise<void>;
    retry: () => void;
  };
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = use(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

/** For screens that sit behind the guard: the signed-in user is guaranteed. */
export function useSignedIn(): { user: User; workspace: Workspace } {
  const { state } = useAuth();
  if (state.status !== "authenticated") throw new Error("useSignedIn used outside an authenticated route");
  return { user: state.user, workspace: state.workspace };
}
