import { expect, test, type Page } from "@playwright/test";
import { mockAdminApi } from "./admin-mock";
import { mockApi } from "./mock-api";

/**
 * The document never scrolls: the shell is exactly one viewport tall and every scrolling region is contained.
 * Checked on every route, phone and desktop, light and dark (one test per route, run by every project).
 */
async function documentOverflow(page: Page) {
  return page.evaluate(() => {
    const root = document.scrollingElement ?? document.documentElement;
    return { vertical: root.scrollHeight - root.clientHeight, horizontal: root.scrollWidth - root.clientWidth };
  });
}

async function expectNoDocumentScroll(page: Page) {
  // Let the route settle (data, entrance animation) before measuring.
  await page.waitForTimeout(700);
  expect(await documentOverflow(page)).toEqual({ vertical: 0, horizontal: 0 });
}

const SIGNED_IN = [
  { path: "/", heading: "New conversation" },
  { path: "/inbox", heading: "Inbox" },
  { path: "/knowledge", heading: "Knowledge" },
  { path: "/team", heading: "Team" },
];

test.describe("the document does not scroll", () => {
  for (const { path, heading } of SIGNED_IN) {
    test(`signed in, ${path}`, async ({ page }) => {
      await mockAdminApi(page, { role: "admin" });
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
      await expectNoDocumentScroll(page);
    });
  }

  test("a page the role may not open", async ({ page }) => {
    await mockApi(page, { role: "user", signedIn: true });
    await page.goto("/team");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoDocumentScroll(page);
  });

  test("a route that does not exist", async ({ page }) => {
    await mockApi(page, { role: "admin", signedIn: true });
    await page.goto("/no-such-page");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoDocumentScroll(page);
  });

  for (const path of ["/sign-in", "/accept", "/reset-password"]) {
    test(`signed out, ${path}`, async ({ page }) => {
      await mockApi(page);
      await page.goto(path);
      await expect(page.getByRole("heading").first()).toBeVisible();
      await expectNoDocumentScroll(page);
    });
  }

  test("a long conversation scrolls inside the list, not the page", async ({ page }) => {
    const { mockChat } = await import("./chat-mock");
    await mockApi(page, { role: "user", signedIn: true });
    const chat = await mockChat(page);
    const messages = Array.from({ length: 40 }, (_, index) => ({
      role: index % 2 === 0 ? ("user" as const) : ("assistant" as const),
      text: `Message number ${index + 1}. ` + "A sentence that makes the line long enough to wrap on a phone. ".repeat(3),
      created_at: new Date(Date.now() - (60 - index) * 60_000).toISOString(),
    }));
    const conversation = chat.seed({ title: "A long one", messages });
    await page.goto(`/?c=${conversation.conversation_id}`);
    await expect(page.getByText("Message number 40.")).toBeVisible();
    await expectNoDocumentScroll(page);
  });
});
