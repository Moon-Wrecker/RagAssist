import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { citation, frame, mockChat, type ChatMock } from "./chat-mock";
import { mockApi } from "./mock-api";

/**
 * Design-review captures of Chat (empty, a conversation with a source and an approval row, the citation panel) in
 * every project: phone and desktop, light and dark. Runs only when E2E_SCREENSHOT_DIR is set; the images are
 * git-ignored. This is a capture script, not coverage.
 */
const dir = process.env.E2E_SCREENSHOT_DIR;
test.skip(!dir, "set E2E_SCREENSHOT_DIR to capture the design review screenshots");

async function shot(page: Page, info: TestInfo, name: string) {
  const out = join(process.cwd(), dir!);
  mkdirSync(out, { recursive: true });
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(out, `${name}-${info.project.name}.png`) });
}

async function open(page: Page, url: string, prepare?: (chat: ChatMock) => void): Promise<ChatMock> {
  await mockApi(page, { role: "user", signedIn: true });
  const chat = await mockChat(page);
  prepare?.(chat);
  await page.goto(url);
  return chat;
}

const iso = (offset: number) => new Date(Date.now() - offset).toISOString();

test("chat, empty", async ({ page }, info) => {
  await open(page, "/", (chat) => {
    chat.seed({ title: "Invoice question", messages: [{ role: "user", text: "Where is my invoice?", created_at: iso(5000) }] });
    chat.seed({ title: "Password reset", status: "resolved", messages: [{ role: "user", text: "I cannot sign in.", created_at: iso(9000) }] });
    chat.seed({ title: "Change my billing email", messages: [{ role: "user", text: "Change it please.", created_at: iso(12000) }] });
  });
  await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
  await shot(page, info, "chat-empty");
});

test("chat, a conversation with a source and an approval row", async ({ page }, info) => {
  const answer =
    "Refunds are issued to the original payment method within 5 business days of approval [1].\n\n" +
    "If the money has not arrived after that, check with your bank first, then ask here and I will look at the payment with you [1].\n\n" +
    "- Card payments: 5 business days\n- Bank transfers: up to 10 business days";
  const seeded = { conversationId: "" };
  const chat = await open(page, "/", (c) => {
    const conversation = c.seed({
      title: "How long do refunds take?",
      messages: [
        { role: "user", text: "How long do refunds take?", created_at: iso(240_000) },
        { role: "assistant", text: answer, citations: [citation], created_at: iso(230_000) },
        { role: "user", text: "Thanks. Can you also check my invoice from last month?", created_at: iso(120_000) },
        { role: "assistant", text: "Your invoice for last month is in Billing, under Invoices. It was issued on the 1st and paid by card [1].", citations: [citation], created_at: iso(110_000) },
      ],
    });
    seeded.conversationId = conversation.conversation_id;
    c.seed({ title: "Invoice question", messages: [{ role: "user", text: "Where is my invoice?", created_at: iso(500_000) }] });
    c.seed({ title: "Password reset", status: "resolved", messages: [{ role: "user", text: "I cannot sign in.", created_at: iso(900_000) }] });
    c.script(() => ({
      frames: [
        frame("tool_call", { tool: "get_account", status: "started" }),
        frame("tool_call", { tool: "get_account", status: "completed" }),
        frame("token", { text: "I can change that for you. Please confirm the new address below." }),
        frame("interrupt", {
          interrupt_id: "interrupt-1",
          action: "approval_required",
          tool: "update_billing_email",
          arguments: { new_email: "new.address@example.test" },
          call_id: "call_1",
        }),
        frame("done", { status: "interrupted" }),
      ],
    }));
  });
  void chat;
  await page.goto(`/?c=${seeded.conversationId}`);
  await expect(page.getByText("Your invoice for last month")).toBeVisible();
  const box = page.getByRole("textbox", { name: /^Message/ });
  await box.fill("Change my billing email to new.address@example.test");
  await box.press("Enter");
  await expect(page.getByRole("group", { name: "Needs your approval" })).toBeVisible();
  await shot(page, info, "chat-conversation");

  await page.getByRole("button", { name: "Source 1: Billing FAQ" }).first().click();
  await expect(page.getByRole("dialog", { name: "Source 1" })).toBeVisible();
  await shot(page, info, "chat-citation-panel");
});
