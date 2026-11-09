import { expect, test } from "@playwright/test";
import { mockApi, type Role } from "./mock-api";

const NAV: Record<Role, string[]> = {
  user: ["Chat"],
  agent: ["Chat", "Inbox"],
  admin: ["Chat", "Inbox", "Knowledge", "Team"],
};

test.describe("session and role-aware shell", () => {
  for (const role of ["user", "agent", "admin"] as const) {
    test(`${role} sees exactly their navigation`, async ({ page }) => {
      await mockApi(page, { role, signedIn: true });
      await page.goto("/");
      const nav = page.getByRole("navigation", { name: "Main" });
      await expect(nav.getByRole("link")).toHaveText(NAV[role]);
    });
  }

  test("restores the session after a reload from the refresh cookie", async ({ page }) => {
    const api = await mockApi(page, { signedIn: true });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
    expect(api.requests.filter((r) => r.path === "/v1/auth/refresh").length).toBeGreaterThanOrEqual(2);
  });

  test("keeps the access token out of storage and the URL", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
    const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }) + document.cookie);
    expect(stored).not.toContain("test-access-");
    expect(page.url()).not.toContain("test-access-");
  });

  test("a customer who opens an admin page is told plainly and can go back", async ({ page }) => {
    await mockApi(page, { role: "user", signedIn: true });
    await page.goto("/team");
    await expect(page.getByRole("heading", { name: /not available to your role/i })).toBeVisible();
    await page.getByRole("link", { name: "Back to chat" }).click();
    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
  });

  test("a signed-out visit to a protected page goes to sign-in", async ({ page }) => {
    await mockApi(page);
    await page.goto("/team");
    await expect(page).toHaveURL(/\/sign-in$/);
  });

  test("an admin can open the team page", async ({ page }) => {
    await mockApi(page, { role: "admin", signedIn: true });
    await page.goto("/team");
    await expect(page.getByRole("heading", { name: "Team" })).toBeVisible();
  });

  test("Ctrl+K opens the palette, filters, navigates and closes", async ({ page }) => {
    await mockApi(page, { role: "admin", signedIn: true });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
    await page.keyboard.press("Control+k");
    const palette = page.getByRole("dialog", { name: "Command palette" });
    await expect(palette).toBeVisible();
    await page.keyboard.type("team");
    await page.keyboard.press("Enter");
    await expect(palette).toBeHidden();
    await expect(page.getByRole("heading", { name: "Team" })).toBeVisible();
  });

  test("the palette button works without a keyboard shortcut", async ({ page }) => {
    await mockApi(page, { signedIn: true });
    await page.goto("/");
    await page.getByRole("button", { name: "Open the command palette" }).click();
    await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test("signing out ends the session and returns to sign-in", async ({ page }) => {
    const api = await mockApi(page, { signedIn: true });
    await page.goto("/");
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/sign-in$/);
    expect(api.requests.some((r) => r.path === "/v1/auth/logout")).toBe(true);
    await page.reload();
    await expect(page).toHaveURL(/\/sign-in$/);
  });

  test("the page does not scroll sideways", async ({ page }) => {
    await mockApi(page, { role: "admin", signedIn: true });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
