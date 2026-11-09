import { expect, test, type Page } from "@playwright/test";
import { fakeCredentials, mockApi } from "./mock-api";

async function fillSignIn(page: Page, values = fakeCredentials()) {
  await page.getByLabel("Workspace").fill(values.workspace);
  await page.getByLabel("Email").fill(values.email);
  await page.getByLabel("Password").fill(values.password);
  return values;
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test.describe("sign-in", () => {
  test("shows the form with labelled fields and fits the viewport", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    await expect(page).toHaveURL(/\/sign-in$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByLabel("Workspace")).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await noHorizontalScroll(page);
  });

  test("signs in and lands on the chat page", async ({ page }) => {
    const api = await mockApi(page);
    await page.goto("/sign-in");
    const values = await fillSignIn(page);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
    expect(api.lastBody("/v1/auth/login")).toEqual(values);
    await noHorizontalScroll(page);
  });

  test("a wrong password gets one generic message announced politely and keeps the form", async ({ page }) => {
    await mockApi(page, { loginStatus: 401 });
    await page.goto("/sign-in");
    await fillSignIn(page);
    await page.getByRole("button", { name: "Sign in" }).click();
    const message = page.locator('[aria-live="polite"]', { hasText: "workspace, email or password is not right" });
    await expect(message).toBeVisible();
    await expect(page.getByLabel("Password")).toHaveAttribute("aria-invalid", "true");
    await expect(page).toHaveURL(/\/sign-in$/);
  });

  test("a throttled sign-in says how long to wait", async ({ page }) => {
    await mockApi(page, { loginStatus: 429 });
    await page.goto("/sign-in");
    await fillSignIn(page);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText(/Wait 2 minutes/)).toBeVisible();
  });

  test("is operable by keyboard alone", async ({ page }) => {
    await mockApi(page);
    await page.goto("/sign-in");
    await expect(page.getByLabel("Workspace")).toBeVisible();
    const values = fakeCredentials();
    await page.keyboard.press("Tab"); // skip link
    await page.keyboard.press("Tab"); // theme toggle
    await page.keyboard.press("Tab"); // workspace
    await expect(page.getByLabel("Workspace")).toBeFocused();
    await page.keyboard.type(values.workspace);
    await page.keyboard.press("Tab");
    await page.keyboard.type(values.email);
    await page.keyboard.press("Tab");
    await page.keyboard.type(values.password);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
  });

  test("the theme toggle switches between light and dark and is remembered", async ({ page }) => {
    await mockApi(page);
    await page.goto("/sign-in");
    const html = page.locator("html");
    const start = await html.getAttribute("data-theme");
    expect(["light", "dark"]).toContain(start);
    // System -> Light -> Dark -> System
    const toggle = page.getByRole("button", { name: /^Theme:/ });
    await toggle.click();
    await expect(html).toHaveAttribute("data-theme", "light");
    await toggle.click();
    await expect(html).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "dark");
  });
});
