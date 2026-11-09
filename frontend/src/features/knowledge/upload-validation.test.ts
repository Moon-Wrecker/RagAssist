import { describe, expect, it } from "vitest";
import { ACCEPT_ATTRIBUTE, MAX_UPLOAD_BYTES, mimeForName, validateUpload } from "./upload-validation";

describe("validateUpload", () => {
  it("accepts each supported type and reports the type to send", () => {
    expect(validateUpload({ name: "handbook.pdf", size: 1000 })).toEqual({ ok: true, mime: "application/pdf" });
    expect(validateUpload({ name: "notes.md", size: 10 })).toEqual({ ok: true, mime: "text/markdown" });
    expect(validateUpload({ name: "notes.markdown", size: 10 })).toEqual({ ok: true, mime: "text/markdown" });
    expect(validateUpload({ name: "page.html", size: 10 })).toEqual({ ok: true, mime: "text/html" });
    expect(validateUpload({ name: "page.htm", size: 10 })).toEqual({ ok: true, mime: "text/html" });
    expect(validateUpload({ name: "prices.csv", size: 10 })).toEqual({ ok: true, mime: "text/csv" });
  });

  it("ignores the case of the extension", () => {
    expect(validateUpload({ name: "HANDBOOK.PDF", size: 5 }).ok).toBe(true);
  });

  it("refuses an unsupported type and names the ones that work", () => {
    const result = validateUpload({ name: "slides.pptx", size: 5 });
    expect(result).toMatchObject({ ok: false, code: "type" });
    expect(result.ok ? "" : result.reason).toMatch(/PDF, Markdown, HTML, CSV/);
  });

  it("refuses a name with no extension, and a dotfile", () => {
    expect(validateUpload({ name: "README", size: 5 }).ok).toBe(false);
    expect(validateUpload({ name: ".pdf", size: 5 }).ok).toBe(false);
  });

  it("refuses an empty file", () => {
    expect(validateUpload({ name: "a.pdf", size: 0 })).toMatchObject({ ok: false, code: "empty" });
  });

  it("allows exactly the size limit and refuses one byte more, with the size in the message", () => {
    expect(validateUpload({ name: "a.pdf", size: MAX_UPLOAD_BYTES }).ok).toBe(true);
    const over = validateUpload({ name: "big.pdf", size: MAX_UPLOAD_BYTES + 1 });
    expect(over).toMatchObject({ ok: false, code: "too-large" });
    expect(over.ok ? "" : over.reason).toMatch(/limit is 50 MB/);
  });

  it("checks the type before the size, so the first thing to fix is the type", () => {
    expect(validateUpload({ name: "big.exe", size: MAX_UPLOAD_BYTES + 1 })).toMatchObject({ code: "type" });
  });
});

describe("helpers", () => {
  it("offers the picker only the supported extensions", () => {
    expect(ACCEPT_ATTRIBUTE.split(",")).toEqual([".pdf", ".md", ".markdown", ".html", ".htm", ".csv"]);
  });
  it("finds a type by file name", () => {
    expect(mimeForName("x.csv")).toBe("text/csv");
    expect(mimeForName("x.txt")).toBeNull();
  });
});
