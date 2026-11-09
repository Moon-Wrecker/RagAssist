import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { Role } from "@/api/types";
import { fakeSession } from "@/test/helpers";
import { AuthContext, type AuthContextValue, type AuthState } from "./auth-context";
import { PublicOnly, RequireAuth, RequireRole } from "./guards";

function stateFor(status: AuthState["status"], role: Role = "user"): AuthState {
  if (status !== "authenticated") return { status } as AuthState;
  const { user, workspace } = fakeSession("unused", role);
  return { status, user, workspace };
}

function valueFor(state: AuthState): AuthContextValue {
  return {
    state,
    actions: { signIn: vi.fn(), acceptLink: vi.fn(), signOut: vi.fn(), retry: vi.fn() },
  };
}

function Where() {
  const location = useLocation();
  return <p>at {location.pathname}</p>;
}

function renderAt(path: string, state: AuthState, initial?: unknown) {
  return render(
    <AuthContext value={valueFor(state)}>
      <MemoryRouter initialEntries={[{ pathname: path, state: initial }]}>
        <Routes>
          <Route element={<PublicOnly />}>
            <Route path="/sign-in" element={<p>sign-in screen</p>} />
          </Route>
          <Route element={<RequireAuth />}>
            <Route path="/" element={<p>chat screen</p>} />
            <Route element={<RequireRole roles={["agent", "admin"]} />}>
              <Route path="/inbox" element={<p>inbox screen</p>} />
            </Route>
            <Route element={<RequireRole roles={["admin"]} />}>
              <Route path="/team" element={<p>team screen</p>} />
            </Route>
          </Route>
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </AuthContext>,
  );
}

describe("RequireAuth", () => {
  it("shows a restoring message while the session is being restored", () => {
    renderAt("/", stateFor("loading"));
    expect(screen.getByText("Restoring your session")).toBeInTheDocument();
  });

  it("sends anonymous visitors to sign-in", () => {
    renderAt("/inbox", stateFor("anonymous"));
    expect(screen.getByText("sign-in screen")).toBeInTheDocument();
  });

  it("offers a retry, not a sign-in, when the server is unreachable", () => {
    renderAt("/", stateFor("unreachable"));
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText("sign-in screen")).not.toBeInTheDocument();
  });

  it("lets signed-in users through", () => {
    renderAt("/", stateFor("authenticated"));
    expect(screen.getByText("chat screen")).toBeInTheDocument();
  });
});

describe("RequireRole", () => {
  it("blocks a customer from the inbox with a plain explanation", () => {
    renderAt("/inbox", stateFor("authenticated", "user"));
    expect(screen.queryByText("inbox screen")).not.toBeInTheDocument();
    expect(screen.getByText(/not available to your role/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to chat" })).toBeInTheDocument();
  });

  it("lets an agent into the inbox but not the team page", () => {
    renderAt("/inbox", stateFor("authenticated", "agent"));
    expect(screen.getByText("inbox screen")).toBeInTheDocument();
  });

  it("blocks an agent from the team page", () => {
    renderAt("/team", stateFor("authenticated", "agent"));
    expect(screen.queryByText("team screen")).not.toBeInTheDocument();
  });

  it("lets an admin into the team page", () => {
    renderAt("/team", stateFor("authenticated", "admin"));
    expect(screen.getByText("team screen")).toBeInTheDocument();
  });
});

describe("PublicOnly", () => {
  it("shows sign-in to anonymous visitors", () => {
    renderAt("/sign-in", stateFor("anonymous"));
    expect(screen.getByText("sign-in screen")).toBeInTheDocument();
  });

  it("sends a signed-in user on to the page they asked for", () => {
    renderAt("/sign-in", stateFor("authenticated", "admin"), { from: { pathname: "/team" } });
    expect(screen.getByText("team screen")).toBeInTheDocument();
  });

  it("falls back to home when their role cannot open the requested page", () => {
    renderAt("/sign-in", stateFor("authenticated", "user"), { from: { pathname: "/team" } });
    expect(screen.getByText("chat screen")).toBeInTheDocument();
  });
});
