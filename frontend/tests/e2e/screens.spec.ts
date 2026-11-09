import { randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { test } from "@playwright/test";
import { mockApi } from "./mock-api";

/**
 * Design review captures: every screen, in every project (phone and desktop, light and dark).
 * Runs only when E2E_SCREENSHOT_DIR is set, for example `E2E_SCREENSHOT_DIR=screenshots npm run e2e`.
 */
const dir = process.env.E2E_SCREENSHOT_DIR;
test.skip(!dir, "set E2E_SCREENSHOT_DIR to capture screens");

test("capture every screen", async ({ page }, info) => {
  const out = join(process.cwd(), dir ?? "screenshots");
  mkdirSync(out, { recursive: true });
  const shot = (name: string) => page.screenshot({ path: join(out, `${name}-${info.project.name}.png`), fullPage: false });

  const api = await mockApi(page, { role: "admin" });
  await page.goto("/sign-in");
  await page.getByLabel("Workspace").waitFor();
  await shot("sign-in");

  await page.getByLabel("Workspace").fill("example");
  await page.getByLabel("Email").fill("person@example.test");
  await page.getByLabel("Password").fill(`pw-${randomUUID()}`);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "Chat" }).waitFor();
  await shot("chat");
  for (const [path, name] of [
    ["/inbox", "inbox"],
    ["/knowledge", "knowledge"],
    ["/team", "team"],
  ] as const) {
    await page.goto(path);
    await page.getByRole("heading", { name: new RegExp(`^${name}$`, "i") }).waitFor();
    await shot(name);
  }

  await page.keyboard.press("Control+k");
  await page.getByRole("dialog", { name: "Command palette" }).waitFor();
  await page.waitForTimeout(250);
  await shot("palette");
  await page.keyboard.press("Escape");

  await page.goto("/sign-in");
  await page.context().clearCookies();
  const fresh = await page.context().newPage();
  await mockApi(fresh);
  const token = `test-link-${randomUUID()}`;
  await fresh.goto(`/accept#token=${token}`);
  await fresh.getByRole("heading", { name: "Set your password" }).waitFor();
  await fresh.screenshot({ path: join(out, `accept-${info.project.name}.png`) });
  await fresh.goto(`/reset-password#token=${token}`);
  await fresh.getByRole("heading", { name: "Choose a new password" }).waitFor();
  await fresh.screenshot({ path: join(out, `reset-${info.project.name}.png`) });
  await fresh.goto("/accept");
  await fresh.getByRole("heading", { name: /incomplete/i }).waitFor();
  await fresh.screenshot({ path: join(out, `link-incomplete-${info.project.name}.png`) });
  void api;
});
