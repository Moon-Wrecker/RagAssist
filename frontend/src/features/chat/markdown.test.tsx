import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Markdown } from "./markdown";
import type { Citation } from "./types";

const citations: Citation[] = [
  { chunkId: "c1", documentId: "d1", title: "Billing FAQ", page: 3, headingPath: ["Billing"] },
  { chunkId: "c2", documentId: "d2", title: "Terms", page: null, headingPath: [] },
];

function renderText(text: string, open = vi.fn()) {
  const view = render(<Markdown text={text} citations={citations} onOpenCitation={open} />);
  return { ...view, open };
}

describe("Markdown of untrusted model text", () => {
  it("never renders a script element or runs its text", () => {
    const { container } = renderText('Before <script>window.__pwned = true</script> after\n\n<script src="https://example.test/x.js"></script>');
    expect(container.querySelector("script")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it("does not parse raw HTML into elements", () => {
    const { container } = renderText('<img src="https://example.test/p.png" onerror="alert(1)"> <b onclick="x()">bold</b> <iframe src="https://example.test"></iframe>');
    expect(container.querySelector("img, iframe, b")).toBeNull();
    expect(container.innerHTML).not.toContain("onerror");
    expect(container.innerHTML).not.toContain("onclick");
  });

  it("removes a javascript: link target but keeps the words", () => {
    const { container } = renderText("[click me](javascript:alert(1)) and [data](data:text/html;base64,AAAA)");
    const hrefs = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href") ?? "");
    for (const href of hrefs) expect(href).not.toMatch(/^(javascript|data):/i);
    expect(container.textContent).toContain("click me");
  });

  it("keeps https links, opening them in a new tab without the opener", () => {
    renderText("See [the docs](https://example.test/docs).");
    const link = screen.getByRole("link", { name: "the docs" });
    expect(link).toHaveAttribute("href", "https://example.test/docs");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("does not load images from the text", () => {
    const { container } = renderText("![tracker](https://example.test/pixel.png)");
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders ordinary markdown: emphasis, lists, tables, code", () => {
    const { container } = renderText("**Bold**\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n`code`");
    expect(container.querySelector("strong")).toHaveTextContent("Bold");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("table")).not.toBeNull();
    expect(container.querySelector("code")).toHaveTextContent("code");
  });
});

describe("citation markers", () => {
  it("turns [n] into a button that opens that source, from any prose element", async () => {
    const { open } = renderText("Refunds take 5 days [1].\n\n- Terms apply [2]\n- Unknown [7]");
    const first = screen.getByRole("button", { name: "Source 1: Billing FAQ" });
    expect(first).toHaveTextContent("1");
    await userEvent.click(first);
    expect(open).toHaveBeenCalledWith(citations[0], 1, first);
    await userEvent.click(screen.getByRole("button", { name: "Source 2: Terms" }));
    expect(open).toHaveBeenLastCalledWith(citations[1], 2, expect.any(HTMLElement));
  });

  it("leaves a marker without a matching citation as plain text", () => {
    const { container } = renderText("Maybe [3] or [9].");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(container.textContent).toContain("[3]");
    expect(container.textContent).toContain("[9]");
  });

  it("does not turn markers inside code into buttons", () => {
    renderText("Use `arr[1]` here.");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
