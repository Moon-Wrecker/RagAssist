import { truncateSync, writeFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { documentRow, mockAdminApi } from "./admin-mock";

const pick = (page: Page, files: { name: string; mimeType: string; buffer: Buffer }[]) =>
  page.getByLabel("Choose documents to upload").setInputFiles(files);

const table = (page: Page) => page.getByRole("table", { name: "Documents the assistant answers from" });

test.describe("knowledge base", () => {
  test("an admin uploads a document and watches it progress to ready, then another fails with a reason", async ({ page }) => {
    const api = await mockAdminApi(page, { role: "admin", documents: [documentRow({ filename: "returns-policy.pdf" })] });
    await page.goto("/knowledge");
    await expect(table(page).getByRole("row", { name: /returns-policy.pdf/ })).toBeVisible();

    await pick(page, [{ name: "handbook.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF placeholder") }]);
    const row = table(page).getByRole("row", { name: /handbook.pdf/ });
    await expect(row).toContainText("Queued");
    expect(api.calls.filter((c) => c.method === "POST" && c.path === "/v1/documents")).toHaveLength(1);

    api.advanceJob(api.lastJobId(), "parsing");
    await expect(row).toContainText("Reading the file", { timeout: 15_000 });
    api.advanceJob(api.lastJobId(), "embedding");
    await expect(row).toContainText("Computing embeddings", { timeout: 15_000 });
    api.advanceJob(api.lastJobId(), "completed");
    await expect(row).toContainText("Ready", { timeout: 15_000 });
    await expect(page.getByRole("status").filter({ hasText: "handbook.pdf is ready." })).toHaveCount(1);

    await pick(page, [{ name: "broken.csv", mimeType: "text/csv", buffer: Buffer.from("a,b\n1,2\n") }]);
    const failing = table(page).getByRole("row", { name: /broken.csv/ });
    await expect(failing).toBeVisible();
    api.advanceJob(api.lastJobId(), "failed", "The file has no readable text.");
    await expect(failing).toContainText("Failed", { timeout: 15_000 });
    await expect(failing).toContainText("Why it failed");
    await expect(failing).toContainText("The file has no readable text.");
  });

  test("the browser's type guess does not matter: the file's extension decides what is sent", async ({ page }) => {
    const api = await mockAdminApi(page, { role: "admin" });
    await page.goto("/knowledge");
    await pick(page, [{ name: "prices.csv", mimeType: "application/vnd.ms-excel", buffer: Buffer.from("a,b\n") }]);
    await expect(table(page).getByRole("row", { name: /prices.csv/ })).toBeVisible();
    expect(api.documents[0]?.contentType).toBe("text/csv");
  });

  test("an unsupported or oversize file is refused on the spot, in plain words, and nothing is sent", async ({ page }, testInfo) => {
    const api = await mockAdminApi(page, { role: "admin" });
    await page.goto("/knowledge");
    // Playwright will not take a buffer over 50 MB, so the oversize file is a sparse file on disk.
    const huge = testInfo.outputPath("huge.pdf");
    writeFileSync(huge, "");
    truncateSync(huge, 51 * 1024 * 1024);
    await page.getByLabel("Choose documents to upload").setInputFiles([
      { name: "slides.pptx", mimeType: "application/octet-stream", buffer: Buffer.from("x") },
    ]);
    await page.getByLabel("Choose documents to upload").setInputFiles([huge]);
    const uploads = page.getByRole("list", { name: "Uploads in progress" });
    await expect(uploads).toContainText("slides.pptx is not a supported type");
    await expect(uploads).toContainText("huge.pdf is 51 MB. The limit is 50 MB per file.");
    expect(api.calls.filter((c) => c.path === "/v1/documents")).toHaveLength(0);
    await page.getByRole("button", { name: "Dismiss the message about slides.pptx" }).click();
    await expect(uploads).not.toContainText("slides.pptx");
  });

  test("when the server refuses a file the reason is shown and the file stays out of the list", async ({ page }) => {
    const api = await mockAdminApi(page, { role: "admin" });
    await page.goto("/knowledge");
    api.failNext("POST /v1/documents", 413, "File exceeds the 50 MB limit.");
    await pick(page, [{ name: "report.pdf", mimeType: "application/pdf", buffer: Buffer.from("x") }]);
    await expect(page.getByRole("list", { name: "Uploads in progress" })).toContainText("report.pdf is larger than the 50 MB limit.");
    await expect(page.getByText("No documents yet.")).toBeVisible();
  });

  test("drag and drop adds a file", async ({ page }) => {
    const api = await mockAdminApi(page, { role: "admin" });
    await page.goto("/knowledge");
    const zone = page.getByRole("group", { name: "Add documents by dropping files" });
    const transfer = await page.evaluateHandle(() => {
      const data = new DataTransfer();
      data.items.add(new File(["# Notes"], "dropped-notes.md", { type: "text/markdown" }));
      return data;
    });
    await zone.dispatchEvent("dragenter", { dataTransfer: transfer });
    await expect(page.getByText("Drop the files to upload them")).toBeVisible();
    await zone.dispatchEvent("drop", { dataTransfer: transfer });
    await expect(table(page).getByRole("row", { name: /dropped-notes.md/ })).toBeVisible();
    expect(api.documents[0]?.contentType).toBe("text/markdown");
  });

  test("re-index queues the document again; delete asks first and can be cancelled", async ({ page }) => {
    const failed = documentRow({ filename: "pricing.html", status: "failed", error: "The page could not be parsed." });
    const keep = documentRow({ filename: "faq.md" });
    const api = await mockAdminApi(page, { role: "admin", documents: [failed, keep] });
    await page.goto("/knowledge");

    const failedRow = table(page).getByRole("row", { name: /pricing.html/ });
    await expect(failedRow).toContainText("The page could not be parsed.");
    await page.getByRole("button", { name: "Re-index pricing.html" }).click();
    await expect(failedRow).toContainText("Queued");
    await expect(failedRow).not.toContainText("Why it failed");
    expect(api.calls.some((c) => c.path === `/v1/documents/${failed.id}/reindex`)).toBe(true);
    await expect(page.getByRole("button", { name: "Re-index pricing.html" })).toBeDisabled();

    // Delete: cancel first, nothing happens.
    await page.getByRole("button", { name: "Delete faq.md" }).click();
    const dialog = page.getByRole("dialog", { name: "Delete this document?" });
    await expect(dialog).toContainText("faq.md");
    await dialog.getByRole("button", { name: "Keep it" }).click();
    await expect(dialog).toBeHidden();
    await expect(table(page).getByRole("row", { name: /faq.md/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Delete faq.md" })).toBeFocused();
    expect(api.calls.some((c) => c.method === "DELETE")).toBe(false);

    // Then confirm.
    await page.getByRole("button", { name: "Delete faq.md" }).click();
    await page.getByRole("dialog", { name: "Delete this document?" }).getByRole("button", { name: "Delete document" }).click();
    await expect(table(page).getByRole("row", { name: /faq.md/ })).toHaveCount(0);
    expect(api.calls.filter((c) => c.method === "DELETE").map((c) => c.path)).toEqual([`/v1/documents/${keep.id}`]);
  });

  test("an empty knowledge base says what to do", async ({ page }) => {
    await mockAdminApi(page, { role: "admin" });
    await page.goto("/knowledge");
    await expect(page.getByText("No documents yet.")).toBeVisible();
    await expect(page.getByText(/Add a PDF, Markdown, HTML or CSV file above/)).toBeVisible();
  });
});
