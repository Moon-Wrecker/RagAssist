import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import { AuthContext, type AuthContextValue } from "@/auth/auth-context";
import { clearCapturedToken } from "@/auth/fragment-token";
import { fakeToken } from "@/test/helpers";
import { ThemeProvider } from "@/theme/theme-provider";
import { AcceptInvitePage } from "./set-password-page";

function setup(acceptLink = vi.fn().mockResolvedValue(undefined)) {
  const value: AuthContextValue = {
    state: { status: "anonymous" },
    actions: { signIn: vi.fn(), acceptLink, signOut: vi.fn(), retry: vi.fn() },
  };
  render(
    <ThemeProvider>
      <AuthContext value={value}>
        <MemoryRouter>
          <AcceptInvitePage />
        </MemoryRouter>
      </AuthContext>
    </ThemeProvider>,
  );
  return acceptLink;
}

beforeEach(() => clearCapturedToken());
afterEach(() => {
  clearCapturedToken();
  window.history.replaceState(null, "", "/");
});

describe("AcceptInvitePage", () => {
  it("reads the token from the fragment, scrubs it from the URL and submits it with the password", async () => {
    const token = fakeToken("link");
    const password = fakeToken("pw");
    window.history.replaceState(null, "", `/accept#token=${token}`);
    const acceptLink = setup();

    expect(window.location.href).not.toContain(token);
    await userEvent.type(screen.getByLabelText("New password"), password);
    await userEvent.type(screen.getByLabelText("Repeat the password"), password);
    await userEvent.click(screen.getByRole("button", { name: /set password/i }));

    await waitFor(() => expect(acceptLink).toHaveBeenCalledWith({ token, password }));
  });

  it("refuses mismatched passwords without calling the server", async () => {
    window.history.replaceState(null, "", `/accept#token=${fakeToken("link")}`);
    const acceptLink = setup();
    await userEvent.type(screen.getByLabelText("New password"), fakeToken("a"));
    await userEvent.type(screen.getByLabelText("Repeat the password"), fakeToken("b"));
    await userEvent.click(screen.getByRole("button", { name: /set password/i }));
    expect(await screen.findByText(/two passwords are different/i)).toBeInTheDocument();
    expect(acceptLink).not.toHaveBeenCalled();
  });

  it("explains an invalid or used link", async () => {
    window.history.replaceState(null, "", `/accept#token=${fakeToken("link")}`);
    setup(vi.fn().mockRejectedValue(new ApiError(401, "link invalid")));
    const password = fakeToken("pw");
    await userEvent.type(screen.getByLabelText("New password"), password);
    await userEvent.type(screen.getByLabelText("Repeat the password"), password);
    await userEvent.click(screen.getByRole("button", { name: /set password/i }));
    expect(await screen.findByText(/ask a workspace admin for a new one/i)).toBeInTheDocument();
  });

  it("shows a plain message when the link has no token", () => {
    window.history.replaceState(null, "", "/accept");
    setup();
    expect(screen.getByRole("heading", { name: /link is incomplete/i })).toBeInTheDocument();
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });
});
