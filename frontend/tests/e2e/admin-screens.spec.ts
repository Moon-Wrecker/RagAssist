import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { test, type Page, type TestInfo } from "@playwright/test";
import { documentRow, escalation, invite, member, mockAdminApi } from "./admin-mock";

/**
 * Design review captures for the inbox, knowledge and team screens: every state, in every project (phone and
 * desktop, light and dark). Runs only when E2E_SCREENSHOT_DIR is set.
 */
const dir = process.env.E2E_SCREENSHOT_DIR;
test.skip(!dir, "set E2E_SCREENSHOT_DIR to capture screens");

function shooter(page: Page, info: TestInfo) {
  const out = join(process.cwd(), dir ?? "screenshots");
  mkdirSync(out, { recursive: true });
  return async (name: string, fullPage = false) => {
    await page.waitForTimeout(350);
    await page.screenshot({ path: join(out, `admin-${name}-${info.project.name}.png`), fullPage });
  };
}

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

test("inbox states", async ({ page }, info) => {
  const shot = shooter(page, info);
  const open = escalation({
    title: "Cannot log in to my account after the password reset",
    messages: [
      { role: "user", text: "I reset my password but the new one is refused.", created_at: minutesAgo(40) },
      { role: "assistant", text: "I could not find this in the documents, so I have asked a colleague to help.", created_at: minutesAgo(39) },
      { role: "agent", text: "Hello, I am looking at your account now.", created_at: minutesAgo(30) },
      { role: "user", text: "Thank you. I used the link from the email twice.", created_at: minutesAgo(20) },
    ],
  });
  const second = escalation({ title: "Refund for a duplicate order", updatedAt: minutesAgo(95) });
  const third = escalation({ title: "Invoice needs a different billing address", updatedAt: minutesAgo(240) });
  const done = escalation({ title: "How do I export my data", status: "resolved", updatedAt: minutesAgo(600) });
  await mockAdminApi(page, { role: "agent", escalations: [open, second, third, done] });

  await page.goto("/inbox");
  await page.getByRole("list", { name: "Conversations" }).waitFor();
  await shot("inbox-list");
  await page.goto(`/inbox?thread=${open.id}`);
  await page.getByRole("log", { name: "Messages" }).waitFor();
  await shot("inbox-thread");
  await page.getByLabel("Reply to the customer").fill("Thanks. I have sent a fresh link; it works for one hour.");
  await shot("inbox-thread-reply");
  await page.getByRole("button", { name: "Resolve and hand back" }).click();
  await page.getByText("This conversation is resolved.").waitFor();
  await shot("inbox-thread-resolved");

  const empty = await page.context().newPage();
  const emptyShot = shooter(empty, info);
  await mockAdminApi(empty, { role: "agent", escalations: [] });
  await empty.goto("/inbox");
  await empty.getByText("Nothing is waiting for a reply.").waitFor();
  await emptyShot("inbox-empty");
});

test("knowledge states", async ({ page }, info) => {
  const shot = shooter(page, info);
  const api = await mockAdminApi(page, {
    role: "admin",
    documents: [
      documentRow({ filename: "returns-policy.pdf", createdAt: minutesAgo(300) }),
      documentRow({ filename: "shipping-faq.md", size: 18_400, createdAt: minutesAgo(200), status: "processing" }),
      documentRow({ filename: "price-list.csv", size: 6_100, createdAt: minutesAgo(5), status: "queued" }),
      documentRow({
        filename: "old-pricing-page.html",
        size: 90_300,
        createdAt: minutesAgo(1500),
        status: "failed",
        error: "The page contains no readable text.",
      }),
    ],
  });
  await page.goto("/knowledge");
  await page.getByRole("table", { name: "Documents the assistant answers from" }).waitFor();
  await shot("knowledge");
  await shot("knowledge-full", true);

  await page.getByLabel("Choose documents to upload").setInputFiles([
    { name: "slides.pptx", mimeType: "application/octet-stream", buffer: Buffer.from("x") },
  ]);
  await page.getByRole("list", { name: "Uploads in progress" }).waitFor();
  await shot("knowledge-rejected");

  await page.getByRole("button", { name: "Actions for shipping-faq.md" }).click();
  await shot("knowledge-row-menu");
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("dialog", { name: "Delete this document?" }).waitFor();
  await shot("knowledge-delete");
  await page.keyboard.press("Escape");

  api.documents.length = 0;
  await page.reload();
  await page.getByText("No documents yet.").waitFor();
  await shot("knowledge-empty");
});

test("team states", async ({ page }, info) => {
  const shot = shooter(page, info);
  const api = await mockAdminApi(page, { role: "admin" });
  api.members.push(
    member(api.selfEmail, "admin", { id: api.selfId }),
    member("priya.nair@example.test", "agent"),
    member("tomas.weber@example.test", "user"),
    member("lena.ortiz@example.test", "user", { status: "disabled" }),
    member("new.hire@example.test", "agent", { has_password: false }),
  );
  api.invites.push(invite("contractor@example.test", "user"), invite("priya.nair@example.test", "agent", "reset"));
  await page.goto("/team");
  await page.getByRole("table", { name: "Members of this workspace" }).waitFor();
  await shot("team");
  await shot("team-full", true);

  await page.getByRole("button", { name: "Actions for tomas.weber@example.test" }).click();
  await shot("team-row-menu");
  await page.getByRole("menuitem", { name: "Deactivate" }).click();
  await page.getByRole("dialog", { name: "Deactivate this member?" }).waitFor();
  await shot("team-deactivate");
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Invite", exact: true }).click();
  await page.getByRole("dialog", { name: "Invite someone" }).waitFor();
  await shot("team-invite");
  await page.getByLabel("Email address").fill("sam.rivera@example.test");
  await page.getByRole("button", { name: "Create invite link" }).click();
  await page.getByRole("dialog", { name: "Invite link ready" }).waitFor();
  await shot("team-link");
  await page.getByRole("button", { name: "Done" }).click();

  api.invites.length = 0;
  await page.reload();
  await page.getByText("No links waiting.").waitFor();
  await shot("team-no-links", true);
});

test("role gate", async ({ page }, info) => {
  const shot = shooter(page, info);
  await mockAdminApi(page, { role: "user" });
  await page.goto("/team");
  await page.getByRole("heading", { name: /not available to your role/i }).waitFor();
  await shot("blocked");
});

// Loading skeletons (the request never answers) and error states (the request fails), one page each.
for (const [name, role, path, apiPath] of [
  ["inbox", "agent", "/inbox", "**/v1/escalations*"],
  ["knowledge", "admin", "/knowledge", "**/v1/documents*"],
  ["team", "admin", "/team", "**/v1/team/members*"],
] as const) {
  test(`${name} loading and error`, async ({ page }, info) => {
    const shot = shooter(page, info);
    await mockAdminApi(page, { role });
    await page.route(apiPath, () => {
      // Never answered: the skeleton stays.
    });
    await page.goto(path);
    await page.getByRole("status", { name: /^Loading/ }).first().waitFor();
    await shot(`${name}-loading`);

    const failing = await page.context().newPage();
    const failShot = shooter(failing, info);
    await mockAdminApi(failing, { role });
    await failing.route(apiPath, (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Unavailable" }) }));
    await failing.goto(path);
    await failing.getByRole("alert").first().waitFor({ timeout: 20_000 });
    await failShot(`${name}-error`);
  });
}
