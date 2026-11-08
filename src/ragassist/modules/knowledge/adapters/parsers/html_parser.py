"""HTML document parser adapter (ADR 0003).

Goal: Parse HTML documents into structured Block objects stripping script/style tags,
converting tables into Markdown table representation, and tracking heading hierarchy.

Consulted documentation & references:
- Python standard library html.parser (https://docs.python.org/3/library/html.parser.html)
- W3C HTML5 DOM traversal principles
- Markdown table formatting rules for parsed HTML tables
"""

from __future__ import annotations

import re
from html.parser import HTMLParser as StdHTMLParser
from pathlib import Path
from typing import Any

from ragassist.modules.knowledge.domain import Block, ParsedDocument, ParseError


class _DOMBuilder(StdHTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.doc_title: str | None = None
        self.blocks: list[Block] = []
        self.heading_stack: list[str] = []

        self._in_script = False
        self._in_style = False
        self._in_title = False
        self._current_tag: str | None = None
        self._buffer: list[str] = []

        # Table parsing state
        self._in_table = False
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._current_tag = tag

        if tag == "script":
            self._in_script = True
        elif tag == "style":
            self._in_style = True
        elif tag == "title":
            self._in_title = True
        elif tag == "table":
            self._flush_text()
            self._in_table = True
            self._table_rows = []
        elif tag == "tr" and self._in_table:
            self._current_row = []
        elif tag in ("td", "th") and self._in_table:
            self._current_cell = []
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_text()
            self._buffer = []
        elif tag in ("p", "div", "section", "article"):
            self._flush_text()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag == "script":
            self._in_script = False
        elif tag == "style":
            self._in_style = False
        elif tag == "title":
            self._in_title = False
            title_text = "".join(self._buffer).strip()
            if title_text and self.doc_title is None:
                self.doc_title = title_text
            self._buffer = []
        elif tag in ("td", "th") and self._in_table:
            cell_text = "".join(self._current_cell).strip()
            self._current_row.append(cell_text)
            self._current_cell = []
        elif tag == "tr" and self._in_table:
            if self._current_row:
                self._table_rows.append(self._current_row)
            self._current_row = []
        elif tag == "table" and self._in_table:
            self._in_table = False
            if self._table_rows:
                # Format as markdown table
                header = self._table_rows[0]
                col_count = len(header)
                header_line = "| " + " | ".join(header) + " |"
                sep_line = "| " + " | ".join(["---"] * col_count) + " |"
                table_lines = [header_line, sep_line]
                for r in self._table_rows[1:]:
                    # Pad row if necessary
                    padded = r + [""] * (col_count - len(r))
                    table_lines.append("| " + " | ".join(padded[:col_count]) + " |")

                self.blocks.append(
                    Block(
                        kind="table",
                        text="\n".join(table_lines),
                        heading_path=tuple(self.heading_stack),
                        page=None,
                    )
                )
            self._table_rows = []
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            h_text = "".join(self._buffer).strip()
            self._buffer = []
            if h_text:
                if self.doc_title is None and level == 1:
                    self.doc_title = h_text
                self.heading_stack = self.heading_stack[: level - 1]
                self.heading_stack.append(h_text)
                self.blocks.append(
                    Block(
                        kind="heading",
                        text=h_text,
                        heading_path=tuple(self.heading_stack),
                        page=None,
                    )
                )
        elif tag in ("p", "div", "li"):
            self._flush_text()

    def handle_data(self, data: str) -> None:
        if self._in_script or self._in_style:
            return

        if self._in_table:
            self._current_cell.append(data)
            return

        self._buffer.append(data)

    def _flush_text(self) -> None:
        if not self._buffer:
            return
        text = " ".join("".join(self._buffer).split())
        self._buffer = []
        if text:
            self.blocks.append(
                Block(
                    kind="paragraph",
                    text=text,
                    heading_path=tuple(self.heading_stack),
                    page=None,
                )
            )


class HtmlParser:
    """Parser for text/html documents."""

    name: str = "html"
    mimes: tuple[str, ...] = ("text/html",)

    def supports(self, mime: str) -> bool:
        return mime in self.mimes

    async def parse(
        self,
        content: bytes,
        *,
        mime: str = "text/html",
        filename: str = "document.html",
    ) -> ParsedDocument:
        if not content:
            return ParsedDocument(title=Path(filename).stem or filename, blocks=[])

        try:
            html_text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                html_text = content.decode("latin-1")
            except Exception as exc:
                raise ParseError(f"Failed to decode HTML content: {exc}") from exc

        parser = _DOMBuilder()
        try:
            parser.feed(html_text)
            parser.close()
            parser._flush_text()
        except Exception as exc:
            raise ParseError(f"Failed to parse HTML document: {exc}") from exc

        title = parser.doc_title or Path(filename).stem or filename
        return ParsedDocument(title=title, blocks=parser.blocks)
