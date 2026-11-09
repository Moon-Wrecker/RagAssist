import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { mockApi } from "./mock-api";

test.describe("invite and reset links", () => {
  test("reads the token from the fragment, scrubs it from the URL and spends it once", async ({ page }) => {
    const api = await mockApi(page, { role: "admin" });
    const token = `test-link-${randomUUID()}`;
    const password = `pw-${randomUUID()}`;
    await page.goto(`/accept#token=${token}`);
    await expect(page.getByRole("heading", { name: "Set your password" })).toBeVisible();
    expect(page.url()).not.toContain(token);
    expect(page.url()).not.toContain("#");

    await page.getByLabel("New password").fill(password);
    await page.getByLabel("Repeat the password").fill(password);
    await page.getByRole("button", { name: /set password and sign in/i }).click();

    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
    expect(api.lastBody("/v1/auth/invites/accept")).toEqual({ token, password });
    // The secret never went to the server as part of a URL.
    expect(api.requests.every((r) => !r.path.includes(token))).toBe(true);
  });

  test("the reset page works the same way with its own wording", async ({ page }) => {
    const api = await mockApi(page);
    const token = `test-link-${randomUUID()}`;
    const password = `pw-${randomUUID()}`;
    await page.goto(`/reset-password#token=${token}`);
    await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
    await page.getByLabel("New password").fill(password);
    await page.getByLabel("Repeat the password").fill(password);
    await page.getByRole("button", { name: /save password and sign in/i }).click();
    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
    expect(api.lastBody("/v1/auth/invites/accept")).toEqual({ token, password });
  });

  test("a link with no token says so and offers sign-in", async ({ page }) => {
    await mockApi(page);
    await page.goto("/accept");
    await expect(page.getByRole("heading", { name: /link is incomplete/i })).toBeVisible();
    await page.getByRole("link", { name: "Go to sign in" }).click();
    await expect(page).toHaveURL(/\/sign-in$/);
  });

  test("mismatched passwords are caught before anything is sent", async ({ page }) => {
    const api = await mockApi(page);
    await page.goto(`/accept#token=test-link-${randomUUID()}`);
    await page.getByLabel("New password").fill(`pw-${randomUUID()}`);
    await page.getByLabel("Repeat the password").fill(`pw-${randomUUID()}`);
    await page.getByRole("button", { name: /set password/i }).click();
    await expect(page.getByText(/two passwords are different/i)).toBeVisible();
    expect(api.requests.some((r) => r.path === "/v1/auth/invites/accept")).toBe(false);
  });

  test("an expired link explains what to do next", async ({ page }) => {
    await mockApi(page, { acceptStatus: 401 });
    await page.goto(`/accept#token=test-link-${randomUUID()}`);
    const password = `pw-${randomUUID()}`;
    await page.getByLabel("New password").fill(password);
    await page.getByLabel("Repeat the password").fill(password);
    await page.getByRole("button", { name: /set password/i }).click();
    await expect(page.getByText(/ask a workspace admin for a new one/i)).toBeVisible();
  });

  test("shows the server's password rule when the password is refused", async ({ page }) => {
    await mockApi(page, { acceptStatus: 422 });
    await page.goto(`/accept#token=test-link-${randomUUID()}`);
    const short = "short";
    await page.getByLabel("New password").fill(short);
    await page.getByLabel("Repeat the password").fill(short);
    await page.getByRole("button", { name: /set password/i }).click();
    await expect(page.getByText("Password must be at least 12 characters.")).toBeVisible();
  });
});
