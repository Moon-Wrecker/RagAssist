import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { citation, frame, mockChat, passage, type ChatMock } from "./chat-mock";
import { mockApi } from "./mock-api";

/**
 * Chat screen against intercepted /v1 calls (no backend). With E2E_SCREENSHOT_DIR set, each state is also captured
 * for the design review, once per project (phone and desktop, light and dark).
 */
const dir = process.env.E2E_SCREENSHOT_DIR;

async function shot(page: Page, info: TestInfo, name: string) {
  if (!dir) return;
  const out = join(process.cwd(), dir);
  mkdirSync(out, { recursive: true });
  await page.waitForTimeout(250);
  await page.screenshot({ path: join(out, `chat-${name}-${info.project.name}.png`) });
}

async function open(page: Page, prepare?: (chat: ChatMock) => void): Promise<ChatMock> {
  await mockApi(page, { role: "user", signedIn: true });
  const chat = await mockChat(page);
  prepare?.(chat);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  return chat;
}

const composer = (page: Page) => page.getByRole("textbox", { name: /^Message/ });

async function ask(page: Page, text: string) {
  await composer(page).fill(text);
  await composer(page).press("Enter");
}

const answerWithCitation = {
  frames: [
    frame("token", { text: "Refunds are issued within " }),
    frame("token", { text: "5 business days [1]." }),
    frame("citation", citation),
    frame("done", { conversation_id: "x", status: "completed" }),
  ],
  save: { text: "Refunds are issued within 5 business days [1].", citations: [citation] },
};

test("empty state tells the person what to do, then an answer streams in with a source", async ({ page }, info) => {
  const chat = await open(page, (c) => c.script(() => answerWithCitation));
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(/^(Still up\?|Good (morning|afternoon|evening)\.)$/);
  await expect(composer(page)).toHaveAttribute("placeholder", "Ask about your account or the documents");
  await shot(page, info, "empty");

  await ask(page, "How long do refunds take?");
  await expect(page.getByText("Refunds are issued within 5 business days")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("How long do refunds take?");
  expect(chat.sent).toEqual(["How long do refunds take?"]);
  await expect(page).toHaveURL(/[?&]c=/);
  await shot(page, info, "answer");

  const marker = page.getByRole("button", { name: "Source 1: Billing FAQ" }).first();
  await marker.click();
  const panel = page.getByRole("dialog", { name: "Source 1" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText(passage.text)).toBeVisible();
  await expect(panel.getByText("Billing / Refunds")).toBeVisible();
  await shot(page, info, "passage");

  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(marker).toBeFocused();
});

test("a passage that no longer exists says so", async ({ page }) => {
  await open(page, (c) =>
    c.script(() => ({
      frames: [frame("token", { text: "See [1]." }), frame("citation", { ...citation, chunk_id: "gone" }), frame("done", { status: "completed" })],
      save: { text: "See [1].", citations: [{ ...citation, chunk_id: "gone" }] },
    })),
  );
  await ask(page, "Where is it written?");
  await page.getByRole("button", { name: /^Source 1/ }).first().click();
  await expect(page.getByRole("alert")).toContainText("no longer available");
});

for (const approved of [true, false]) {
  test(`${approved ? "approve" : "deny"} an action: values shown exactly, composer locked, outcome stays`, async ({ page }, info) => {
    const interrupt = {
      interrupt_id: "interrupt-1",
      action: "approval_required",
      tool: "update_billing_email",
      arguments: { new_email: "new.address@example.test" },
      call_id: "call_1",
    };
    const chat = await open(page, (c) =>
      c.script(() => ({
        frames: [frame("tool_call", { tool: "get_account", status: "started" }), frame("interrupt", interrupt), frame("done", { status: "interrupted" })],
      })),
    );
    await ask(page, "Change my billing email to new.address@example.test");

    const card = page.getByRole("group", { name: "Needs your approval" });
    await expect(card).toBeVisible();
    await expect(card).toContainText("update_billing_email");
    await expect(card).toContainText("new_email");
    await expect(card).toContainText("new.address@example.test");
    await expect(composer(page)).toHaveAttribute("aria-disabled", "true");
    await expect(page.getByText("Locked until you decide on the action above.")).toBeVisible();
    await shot(page, info, "approval");

    await card.getByRole("button", { name: approved ? /^Approve/ : /^Deny/ }).click();
    await expect(page.getByText(approved ? "You approved" : "You denied")).toBeVisible();
    await expect(page.getByText(approved ? "Your billing email is now updated." : "I did not change anything.")).toBeVisible();
    expect(chat.decisions).toEqual([{ interruptId: "interrupt-1", approved }]);
    await expect(composer(page)).not.toHaveAttribute("aria-disabled", "true");
    await expect(card).toBeHidden();
    await shot(page, info, approved ? "approved" : "denied");
  });
}

test("escalation to a support agent: assistant goes silent, the agent's reply arrives live", async ({ page }, info) => {
  const chat = await open(page, (c) =>
    c.script((_content, conversation) =>
      conversation.status === "escalated"
        ? { frames: [frame("escalated", { ticket_id: "TICK-0001", status: "open", priority: "high" }), frame("done", { status: "escalated" })] }
        : {
            frames: [
              frame("token", { text: "I cannot resolve this, so I am handing you to a person." }),
              frame("escalated", { ticket_id: "TICK-0001", status: "open", priority: "high" }),
              frame("done", { status: "escalated" }),
            ],
            save: { text: "I cannot resolve this, so I am handing you to a person." },
            status: "escalated",
          },
    ),
  );
  await ask(page, "I was charged twice and need a person.");
  await expect(page.getByText("A support agent has taken over")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("With a support agent");
  await expect(composer(page)).toHaveAccessibleName("Message to the support agent");
  await shot(page, info, "handoff");

  // The customer writes again: it goes to the agent and the assistant stays silent.
  await ask(page, "Any news?");
  await expect(page.getByText("Any news?", { exact: true })).toBeVisible();
  await expect.poll(() => chat.sent).toEqual(["I was charged twice and need a person.", "Any news?"]);
  await expect(page.getByText("Looking through your documents")).toHaveCount(0);

  // A person replies; the live event refreshes the conversation.
  const conversation = chat.conversations[0]!;
  conversation.messages.push({ role: "agent", text: "Hello, I have found the duplicate charge and refunded it.", created_at: new Date().toISOString() });
  chat.pushEvent("message.created", { conversation_id: conversation.conversation_id });
  await expect(page.getByText("Hello, I have found the duplicate charge and refunded it.")).toBeVisible();
  await expect(page.getByText("Support agent", { exact: true })).toBeVisible();
  await shot(page, info, "agent-reply");

  // Resolving hands the conversation back to the assistant.
  conversation.status = "resolved";
  chat.pushEvent("conversation.updated", { conversation_id: conversation.conversation_id });
  await expect(composer(page)).toHaveAccessibleName("Message");
  await expect(page.getByRole("heading", { level: 1 })).not.toContainText("With a support agent");
});

test("stop abandons the wait, the turn still finishes and its answer is picked up", async ({ page }, info) => {
  const chat = await open(page, (c) =>
    c.script(() => ({ frames: [], hold: true, save: { text: "The long answer, saved after you stopped watching." } })),
  );
  await ask(page, "Summarise every document.");
  await expect(page.getByText("Looking through your documents")).toBeVisible();
  await expect(composer(page)).toHaveAttribute("aria-disabled", "true");
  await shot(page, info, "waiting");

  await page.getByRole("button", { name: "Stop the answer" }).click();
  await expect(page.getByText("Stopped. The assistant may still finish and save this answer.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  await shot(page, info, "stopped");

  chat.finishHeld();
  await expect(page.getByText("The long answer, saved after you stopped watching.")).toBeVisible();
  await expect(page.getByText("Stopped. The assistant may still finish")).toHaveCount(0);
});

test("a failed stream offers to try again", async ({ page }, info) => {
  let attempt = 0;
  const chat = await open(page, (c) =>
    c.script(() => {
      attempt += 1;
      return attempt === 1
        ? { frames: [frame("token", { text: "Part" }), frame("error", { code: "internal_error", message: "An error occurred while processing the request." })] }
        : { frames: [frame("token", { text: "Second time works." }), frame("done", { status: "completed" })], save: { text: "Second time works." } };
    }),
  );
  await ask(page, "Please answer.");
  await expect(page.getByRole("alert")).toContainText("An error occurred while processing the request.");
  await shot(page, info, "error");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("Second time works.")).toBeVisible();
  expect(chat.sent).toEqual(["Please answer.", "Please answer."]);
});

test("history lists conversations and switching opens the chosen thread", async ({ page }, info) => {
  const now = Date.now();
  const iso = (offset: number) => new Date(now - offset).toISOString();
  const chat = await open(page, (c) => {
    c.seed({
      title: "Invoice question",
      messages: [
        { role: "user", text: "Where is my invoice?", created_at: iso(5000) },
        { role: "assistant", text: "Invoices are under Billing.", created_at: iso(4000) },
      ],
    });
    c.seed({
      title: "Password reset",
      status: "resolved",
      messages: [
        { role: "user", text: "I cannot sign in.", created_at: iso(9000) },
        { role: "assistant", text: "Use the reset link.", created_at: iso(8000) },
      ],
    });
  });
  void chat;

  // On a phone the history is a sheet behind the History button; on a desktop it sits in the sidebar.
  const phone = info.project.name.startsWith("phone");
  async function pick(title: RegExp) {
    if (phone) {
      await page.getByRole("button", { name: "History" }).click();
      const sheet = page.getByRole("dialog", { name: "History" });
      await expect(sheet).toBeVisible();
      await sheet.getByRole("button", { name: title }).click();
      await expect(sheet).toBeHidden();
    } else {
      await page.getByRole("complementary", { name: "Sidebar" }).getByRole("button", { name: title }).click();
    }
  }

  const list = phone ? null : page.getByRole("complementary", { name: "Sidebar" });
  if (list) {
    await expect(list.getByRole("button", { name: /Invoice question/ })).toBeVisible();
    await expect(list.getByText("Resolved")).toBeVisible();
  }
  await shot(page, info, "history");

  await pick(/Password reset/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Password reset");
  await expect(page.getByText("Use the reset link.")).toBeVisible();

  await pick(/Invoice question/);
  await expect(page.getByText("Invoices are under Billing.")).toBeVisible();
  await expect(page.getByText("Use the reset link.")).toHaveCount(0);
  await shot(page, info, "switched");
});

// Playwright scrolls an obscured element into view before clicking it. The first source chip can sit under the glass
// header, so the click targets the last chip (the one a reader can reach) to test the panel and not the test driver.
test("opening a source does not push the end of the thread behind the composer", async ({ page }, info) => {
  test.skip(info.project.name.startsWith("phone"), "on a phone the source is a sheet over the thread");
  const iso = (offset: number) => new Date(Date.now() - offset).toISOString();
  const seeded = { id: "" };
  await open(page, (c) => {
    const conversation = c.seed({
      title: "Refunds",
      messages: [
        { role: "user", text: "How long do refunds take?", created_at: iso(240_000) },
        {
          role: "assistant",
          text:
            "Refunds are issued to the original payment method within 5 business days of approval [1].\n\n" +
            "If the money has not arrived after that, check with your bank first, then ask here [1].\n\n" +
            "- Card payments: 5 business days\n- Bank transfers: up to 10 business days",
          citations: [citation],
          created_at: iso(230_000),
        },
        { role: "user", text: "Thanks. Can you also check my invoice from last month?", created_at: iso(120_000) },
        { role: "assistant", text: "Your invoice for last month is in Billing, under Invoices. It was issued on the 1st and paid by card [1].", citations: [citation], created_at: iso(110_000) },
      ],
    });
    seeded.id = conversation.conversation_id;
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
  await page.goto(`/?c=${seeded.id}`);
  await expect(page.getByText("Your invoice for last month")).toBeVisible();
  await ask(page, "Change my billing email to new.address@example.test");
  const card = page.getByRole("group", { name: "Needs your approval" });
  await expect(card).toBeVisible();

  const clear = async () => {
    const [approval, box] = await Promise.all([card.boundingBox(), page.getByRole("form", { name: "Send a message" }).boundingBox()]);
    return box!.y - (approval!.y + approval!.height);
  };
  await expect.poll(clear).toBeGreaterThanOrEqual(0);

  await page.getByRole("button", { name: "Source 1: Billing FAQ" }).last().click();
  await expect(page.getByRole("dialog", { name: "Source 1" })).toBeVisible();
  // The column narrows and rewraps; the approval must still be fully above the composer.
  await expect.poll(clear, { timeout: 3000 }).toBeGreaterThanOrEqual(0);
  await page.waitForTimeout(600);
  expect(await clear()).toBeGreaterThanOrEqual(0);
});
