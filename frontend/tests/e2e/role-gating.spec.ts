import { expect, test } from "@playwright/test";
import { mockAdminApi } from "./admin-mock";

const BLOCKED = /not available to your role/i;

test.describe("role gating for the inbox, knowledge and team pages", () => {
  test("a customer sees none of them, in the navigation or by address, and no data is requested", async ({ page }) => {
    const api = await mockAdminApi(page, { role: "user" });
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link")).toHaveText(["Chat"]);
    for (const path of ["/inbox", "/knowledge", "/team"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: BLOCKED })).toBeVisible();
    }
    const dataCalls = api.calls.filter((c) => /escalations|documents|team/.test(c.path));
    expect(dataCalls).toEqual([]);
  });

  test("the not-allowed page has exactly one main landmark", async ({ page }) => {
    await mockAdminApi(page, { role: "user" });
    await page.goto("/inbox");
    await expect(page.getByRole("heading", { name: BLOCKED })).toBeVisible();
    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.getByRole("main")).toHaveCount(1);
  });

  test("an agent gets the inbox but not knowledge or team", async ({ page }) => {
    await mockAdminApi(page, { role: "agent" });
    await page.goto("/inbox");
    await expect(page.getByRole("heading", { name: "Inbox", level: 1 })).toBeVisible();
    for (const path of ["/knowledge", "/team"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: BLOCKED })).toBeVisible();
    }
  });

  test("an admin gets all three", async ({ page }) => {
    await mockAdminApi(page, { role: "admin" });
    for (const [path, title] of [
      ["/inbox", "Inbox"],
      ["/knowledge", "Knowledge"],
      ["/team", "Team"],
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
    }
  });

  test("the palette offers only the pages the role may open", async ({ page }) => {
    await mockAdminApi(page, { role: "agent" });
    await page.goto("/");
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
    await page.keyboard.press("Control+k");
    const palette = page.getByRole("dialog", { name: "Command palette" });
    await expect(palette.getByRole("option", { name: /Inbox/ })).toBeVisible();
    await expect(palette.getByRole("option", { name: /Team/ })).toHaveCount(0);
    await expect(palette.getByRole("option", { name: /Knowledge/ })).toHaveCount(0);
  });
});
