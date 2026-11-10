import { expect, test } from "@playwright/test";
import { escalation, mockAdminApi } from "./admin-mock";

const isPhone = (width: number | undefined) => (width ?? 1280) < 1024;

test.describe("inbox", () => {
  test("an agent reads a thread, sees a customer message arrive live, replies and resolves", async ({ page }) => {
    const login = escalation({ title: "Cannot log in to my account" });
    const refund = escalation({ title: "Refund for a duplicate order", updatedAt: new Date(Date.now() - 3_600_000).toISOString() });
    const done = escalation({ title: "Invoice address", status: "resolved" });
    const api = await mockAdminApi(page, { role: "agent", escalations: [login, refund, done] });

    await page.goto("/inbox");
    await expect(page.getByRole("heading", { name: "Inbox", level: 1 })).toBeVisible();

    // The list opens on what needs a reply, with counts on the filters.
    const list = page.getByRole("list", { name: "Conversations" });
    await expect(list.getByRole("link")).toHaveCount(2);
    await expect(page.getByRole("button", { name: /Needs a reply/ })).toContainText("2");
    await expect(page.getByRole("button", { name: /Resolved/ })).toContainText("1");

    await list.getByRole("link", { name: /Cannot log in/ }).click();
    await expect(page).toHaveURL(/thread=/);
    await expect(page.getByRole("heading", { name: "Cannot log in to my account", level: 2 })).toBeVisible();
    const log = page.getByRole("log", { name: "Messages" });
    await expect(log).toContainText("Hello, I need help with this.");
    await expect(log).toContainText("Assistant");

    // A customer message arrives through the live stream, without any action by the agent.
    api.customerSays(login.id, "I tried the reset link twice.");
    await expect(log).toContainText("I tried the reset link twice.", { timeout: 15_000 });

    // Reply: it shows at once and goes to the server once.
    await page.getByLabel("Reply to the customer").fill("Thanks, I have sent a fresh link.");
    await page.getByRole("button", { name: "Send reply" }).click();
    await expect(log).toContainText("Thanks, I have sent a fresh link.");
    await expect(page.getByLabel("Reply to the customer")).toHaveValue("");
    expect(api.calls.filter((c) => c.path.endsWith("/reply")).map((c) => c.body)).toEqual([{ text: "Thanks, I have sent a fresh link." }]);
    await expect(log.getByText("Sending")).toHaveCount(0);

    // Resolve: the thread turns read-only and the conversation leaves "Needs a reply".
    await page.getByRole("button", { name: "Resolve and hand back" }).click();
    await expect(page.getByText("This conversation is resolved.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Resolve and hand back" })).toHaveCount(0);
    await expect(page.getByLabel("Reply to the customer")).toHaveCount(0);
    expect(api.calls.some((c) => c.path === `/v1/escalations/${login.id}/resolve`)).toBe(true);
    // On a phone the thread replaces the list, so go back to it first.
    if (isPhone(page.viewportSize()?.width)) await page.getByRole("link", { name: "All conversations" }).click();
    await expect(page.getByRole("button", { name: /Needs a reply/ })).toContainText("1");

    await page.getByRole("button", { name: /Resolved/ }).click();
    await expect(list.getByRole("link", { name: /Cannot log in/ })).toBeVisible();
  });

  test("on a phone the thread replaces the list and a link goes back", async ({ page }) => {
    const item = escalation({ title: "Cannot log in to my account" });
    await mockAdminApi(page, { role: "agent", escalations: [item] });
    await page.goto("/inbox");
    const list = page.getByRole("list", { name: "Conversations" });
    await list.getByRole("link", { name: /Cannot log in/ }).click();
    await expect(page.getByRole("heading", { name: "Cannot log in to my account", level: 2 })).toBeVisible();

    if (isPhone(page.viewportSize()?.width)) {
      await expect(list).toBeHidden();
      await page.getByRole("link", { name: "All conversations" }).click();
      await expect(list).toBeVisible();
      await expect(page.getByRole("heading", { name: "Cannot log in to my account", level: 2 })).toBeHidden();
    } else {
      // Desktop shows both at once.
      await expect(list).toBeVisible();
      await expect(page.getByRole("link", { name: "All conversations" })).toBeHidden();
    }
  });

  test("a failed reply keeps the words and says what happened", async ({ page }) => {
    const item = escalation({ title: "Cannot log in to my account" });
    const api = await mockAdminApi(page, { role: "agent", escalations: [item] });
    await page.goto(`/inbox?thread=${item.id}`);
    await expect(page.getByRole("log", { name: "Messages" })).toBeVisible();
    api.failNext(`POST /v1/escalations/${item.id}/reply`, 409, "This conversation is not escalated.");
    await page.getByLabel("Reply to the customer").fill("Let me look into it.");
    await page.keyboard.press("Control+Enter");
    await expect(page.getByText("This conversation is not escalated.")).toBeVisible();
    await expect(page.getByLabel("Reply to the customer")).toHaveValue("Let me look into it.");
    await expect(page.getByRole("log", { name: "Messages" }).getByText("Let me look into it.")).toHaveCount(0);
  });

  test("an admin can read and resolve but is told only agents reply", async ({ page }) => {
    const item = escalation({ title: "Cannot log in to my account" });
    await mockAdminApi(page, { role: "admin", escalations: [item] });
    await page.goto(`/inbox?thread=${item.id}`);
    await expect(page.getByText("Only support agents can reply.")).toBeVisible();
    await expect(page.getByLabel("Reply to the customer")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Resolve and hand back" })).toBeVisible();
  });

  test("search narrows the list and an empty list says what happens next", async ({ page }) => {
    await mockAdminApi(page, { role: "agent", escalations: [escalation({ title: "Cannot log in" }), escalation({ title: "Refund request" })] });
    await page.goto("/inbox");
    await page.getByLabel("Search conversations").fill("refund");
    const list = page.getByRole("list", { name: "Conversations" });
    await expect(list.getByRole("link")).toHaveCount(1);
    await page.getByLabel("Search conversations").fill("zzz");
    await expect(page.getByText("No conversation matches that search.")).toBeVisible();

    const empty = await page.context().newPage();
    await mockAdminApi(empty, { role: "agent", escalations: [] });
    await empty.goto("/inbox");
    await expect(empty.getByText("Nothing is waiting for a reply.")).toBeVisible();
    await expect(empty.getByText(/New handoffs appear here/)).toBeVisible();
  });

  test("a conversation that is gone is explained", async ({ page }) => {
    await mockAdminApi(page, { role: "agent", escalations: [] });
    await page.goto("/inbox?thread=00000000-0000-4000-8000-000000000000");
    await expect(page.getByText("This conversation is not available.")).toBeVisible();
  });
});
