import { expect, test, type Page } from "@playwright/test";
import { FAKE_LINK_PREFIX, invite, member, mockAdminApi } from "./admin-mock";

const members = (page: Page) => page.getByRole("table", { name: "Members of this workspace" });
const pending = (page: Page) => page.getByRole("table", { name: "Pending invitations and reset links" });

/** Row actions live in a menu at the end of the row. */
async function memberAction(page: Page, email: string, action: string) {
  await page.getByRole("button", { name: `Actions for ${email}` }).click();
  await page.getByRole("menuitem", { name: action }).click();
}

async function openInvite(page: Page) {
  await page.getByRole("button", { name: "Invite", exact: true }).click();
  return page.getByRole("dialog", { name: "Invite someone" });
}

test.beforeEach(async ({ context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
});

test.describe("team", () => {
  test("an admin changes a role, deactivates a member and reactivates them", async ({ page }) => {
    const ann = member("ann@example.test", "user");
    const bo = member("bo@example.test", "agent");
    const api = await mockAdminApi(page, { role: "admin", members: [ann, bo] });
    api.members.push(member(api.selfEmail, "admin", { id: api.selfId }));
    await page.goto("/team");

    await expect(members(page).getByRole("row", { name: new RegExp(ann.email) })).toBeVisible();

    await page.getByLabel(`Role for ${ann.email}`).selectOption("agent");
    await expect(page.getByLabel(`Role for ${ann.email}`)).toHaveValue("agent");
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ role: "agent" });

    await memberAction(page, bo.email, "Deactivate");
    const dialog = page.getByRole("dialog", { name: "Deactivate this member?" });
    await expect(dialog).toContainText(bo.email);
    await dialog.getByRole("button", { name: "Keep them active" }).click();
    await expect(dialog).toBeHidden();
    expect(api.members.find((m) => m.id === bo.id)?.status).toBe("active");

    await memberAction(page, bo.email, "Deactivate");
    await page.getByRole("dialog", { name: "Deactivate this member?" }).getByRole("button", { name: "Deactivate" }).click();
    const boRow = members(page).getByRole("row", { name: new RegExp(bo.email) });
    await expect(boRow).toContainText("Deactivated");
    await page.getByRole("button", { name: `Actions for ${bo.email}` }).click();
    await expect(page.getByRole("menuitem", { name: "Reactivate" })).toBeVisible();
    await page.keyboard.press("Escape");
    expect(api.calls.filter((c) => c.method === "PATCH").at(-1)?.body).toEqual({ status: "disabled" });

    await memberAction(page, bo.email, "Reactivate");
    await expect(boRow).toContainText("Active");
    expect(api.calls.filter((c) => c.method === "PATCH").at(-1)?.body).toEqual({ status: "active" });
  });

  test("your own row cannot be changed", async ({ page }) => {
    const api = await mockAdminApi(page, { role: "admin" });
    api.members.push(member(api.selfEmail, "admin", { id: api.selfId }));
    await page.goto("/team");
    await expect(page.getByLabel(`Role for ${api.selfEmail}`)).toBeDisabled();
    await page.getByRole("button", { name: `Actions for ${api.selfEmail}` }).click();
    await expect(page.getByRole("menuitem", { name: "Deactivate" })).toHaveAttribute("aria-disabled", "true");
  });

  test("a refused change is rolled back and explained", async ({ page }) => {
    const other = member("only-admin@example.test", "admin");
    const api = await mockAdminApi(page, { role: "admin", members: [other] });
    await page.goto("/team");
    api.failNext(`PATCH /v1/team/members/${other.id}`, 409, "A workspace needs at least one active administrator.");
    await page.getByLabel(`Role for ${other.email}`).selectOption("user");
    await expect(page.getByText("A workspace needs at least one active administrator.")).toBeVisible();
    await expect(page.getByLabel(`Role for ${other.email}`)).toHaveValue("admin");
  });

  test("creating an invite shows the link once, copies it, and it can be revoked", async ({ page }) => {
    const api = await mockAdminApi(page, { role: "admin", members: [] });
    await page.goto("/team");
    await expect(page.getByText("No links waiting.")).toBeVisible();

    const form = await openInvite(page);
    await form.getByLabel("Email address").fill("new.person@example.test");
    await form.getByLabel("Role", { exact: true }).selectOption("agent");
    await form.getByRole("button", { name: "Create invite link" }).click();

    const dialog = page.getByRole("dialog", { name: "Invite link ready" });
    await expect(dialog).toContainText("shown only once");
    await expect(dialog).toContainText("new.person@example.test");
    const field = dialog.getByLabel("One-time link");
    const link = await field.inputValue();
    expect(link.startsWith(FAKE_LINK_PREFIX)).toBe(true);
    expect(api.calls.find((c) => c.path === "/v1/team/invites")?.body).toEqual({ email: "new.person@example.test", role: "agent" });

    await dialog.getByRole("button", { name: "Copy link" }).click();
    await expect(dialog.getByText("Copied to the clipboard.")).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(link);

    await dialog.getByRole("button", { name: "Done" }).click();
    await expect(dialog).toBeHidden();
    // The link is gone for good: it is not in the page, and the pending list only has the address.
    expect(await page.content()).not.toContain(link);
    const row = pending(page).getByRole("row", { name: /new.person@example.test/ });
    await expect(row).toContainText("Invitation");
    await expect(row).toContainText("Support agent");

    await page.getByRole("button", { name: "Revoke the invitation for new.person@example.test" }).click();
    await expect(pending(page)).toHaveCount(0);
    await expect(page.getByText("No links waiting.")).toBeVisible();
    expect(api.calls.filter((c) => c.method === "DELETE")).toHaveLength(1);
  });

  test("an address that already has an account is refused in words", async ({ page }) => {
    const existing = member("taken@example.test", "user");
    await mockAdminApi(page, { role: "admin", members: [existing] });
    await page.goto("/team");
    const form = await openInvite(page);
    await form.getByLabel("Email address").fill(existing.email);
    await form.getByRole("button", { name: "Create invite link" }).click();
    await expect(form.getByText("That address already has an account in this workspace.")).toBeVisible();
    // The dialog stays open so the address can be fixed, and no link was issued.
    await expect(page.getByRole("dialog", { name: "Invite link ready" })).toHaveCount(0);
  });

  test("a password reset link is issued for a member and listed as pending", async ({ page }) => {
    const ann = member("ann@example.test", "user");
    const api = await mockAdminApi(page, { role: "admin", members: [ann], invites: [invite("waiting@example.test", "user")] });
    await page.goto("/team");
    await expect(pending(page).getByRole("row", { name: /waiting@example.test/ })).toBeVisible();

    await memberAction(page, ann.email, "Reset password link");
    const dialog = page.getByRole("dialog", { name: "Password reset link ready" });
    await expect(dialog.getByLabel("One-time link")).toHaveValue(new RegExp(`^${FAKE_LINK_PREFIX}`));
    expect(api.calls.some((c) => c.path === `/v1/team/members/${ann.id}/reset-link`)).toBe(true);
    await dialog.getByRole("button", { name: "Done" }).click();
    await expect(pending(page).getByRole("row", { name: /ann@example.test/ })).toContainText("Password reset");
  });

  test("dialogs keep keyboard focus inside and Escape closes them", async ({ page }) => {
    const ann = member("ann@example.test", "user");
    await mockAdminApi(page, { role: "admin", members: [ann] });
    await page.goto("/team");
    await memberAction(page, ann.email, "Deactivate");
    const dialog = page.getByRole("dialog", { name: "Deactivate this member?" });
    for (let i = 0; i < 5; i += 1) {
      await page.keyboard.press("Tab");
      expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("button", { name: `Actions for ${ann.email}` })).toBeFocused();
  });
});
