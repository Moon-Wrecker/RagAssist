"""Markdown document parser adapter (ADR 0003).

Goal: Parse Markdown documents into structured Block objects preserving heading hierarchy,
table structure, and code fences.

Consulted documentation & references:
- CommonMark Specification (https://spec.commonmark.org/0.30/): ATX headings, fenced code blocks, tables
- ADR 0003: Structure-Aware 5-Pass Hybrid Chunking
- Standard UTF-8 / fallback decode error handling
"""

from __future__ import annotations

import re
from typing import Any
from pathlib import Path

from ragassist.modules.knowledge.domain import Block, ParsedDocument, ParseError


class MarkdownParser:
    """Parser for text/markdown documents."""

    name: str = "markdown"
    mimes: tuple[str, ...] = ("text/markdown",)

    def supports(self, mime: str) -> bool:
        return mime in self.mimes

    async def parse(
        self,
        content: bytes,
        *,
        mime: str = "text/markdown",
        filename: str = "document.md",
    ) -> ParsedDocument:
        if not content:
            return ParsedDocument(title=Path(filename).stem or filename, blocks=[])

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as exc:
                raise ParseError(f"Failed to decode markdown content: {exc}") from exc

        lines = text.splitlines()
        blocks: list[Block] = []
        heading_stack: list[str] = []
        doc_title: str | None = None

        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            # Code fence block: ``` or ~~~
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence = stripped[:3]
                code_lines: list[str] = []
                i += 1
                while i < n and not lines[i].strip().startswith(fence):
                    code_lines.append(lines[i])
                    i += 1
                if i < n:
                    i += 1  # consume closing fence
                blocks.append(
                    Block(
                        kind="code",
                        text="\n".join(code_lines),
                        heading_path=tuple(heading_stack),
                        page=None,
                    )
                )
                continue

            # ATX Heading block: # Heading
            heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if heading_match:
                level = len(heading_match.group(1))
                h_text = heading_match.group(2).strip()

                if doc_title is None and level == 1:
                    doc_title = h_text

                # Update heading stack
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(h_text)

                blocks.append(
                    Block(
                        kind="heading",
                        text=h_text,
                        heading_path=tuple(heading_stack),
                        page=None,
                    )
                )
                i += 1
                continue

            # Markdown Table block: lines containing |
            if "|" in stripped:
                table_lines: list[str] = []
                while i < n and "|" in lines[i].strip():
                    table_lines.append(lines[i].strip())
                    i += 1
                blocks.append(
                    Block(
                        kind="table",
                        text="\n".join(table_lines),
                        heading_path=tuple(heading_stack),
                        page=None,
                    )
                )
                continue

            # Markdown List block: - , * , 1.
            if re.match(r"^([-*+]|\d+\.)\s+", stripped):
                list_lines: list[str] = []
                while i < n and (
                    re.match(r"^([-*+]|\d+\.)\s+", lines[i].strip())
                    or (lines[i].startswith(" ") and lines[i].strip())
                ):
                    list_lines.append(lines[i].strip())
                    i += 1
                blocks.append(
                    Block(
                        kind="list",
                        text="\n".join(list_lines),
                        heading_path=tuple(heading_stack),
                        page=None,
                    )
                )
                continue

            # Regular paragraph
            para_lines: list[str] = []
            while (
                i < n
                and lines[i].strip()
                and not lines[i].strip().startswith("#")
                and not lines[i].strip().startswith("```")
                and not lines[i].strip().startswith("~~~")
                and "|" not in lines[i].strip()
                and not re.match(r"^([-*+]|\d+\.)\s+", lines[i].strip())
            ):
                para_lines.append(lines[i].strip())
                i += 1

            blocks.append(
                Block(
                    kind="paragraph",
                    text=" ".join(para_lines),
                    heading_path=tuple(heading_stack),
                    page=None,
                )
            )

        title = doc_title or Path(filename).stem or filename
        return ParsedDocument(title=title, blocks=blocks)
