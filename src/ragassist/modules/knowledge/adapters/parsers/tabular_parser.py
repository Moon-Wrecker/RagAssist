"""Tabular (CSV) document parser adapter (ADR 0003).

Goal: Parse CSV files into row blocks repeating column headers to retain semantic field binding.

Consulted documentation & references:
- RFC 4180 Common Format and MIME Type for Comma-Separated Values (CSV)
- Python standard library csv module (https://docs.python.org/3/library/csv.html)
- ADR 0003 tabular ingestion specifications
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from ragassist.modules.knowledge.domain import Block, ParsedDocument, ParseError


class TabularParser:
    """Parser for text/csv tabular documents."""

    name: str = "tabular"
    mimes: tuple[str, ...] = ("text/csv",)

    def supports(self, mime: str) -> bool:
        return mime in self.mimes

    async def parse(
        self,
        content: bytes,
        *,
        mime: str = "text/csv",
        filename: str = "data.csv",
    ) -> ParsedDocument:
        if not content:
            return ParsedDocument(title=Path(filename).stem or filename, blocks=[])

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as exc:
                raise ParseError(f"Failed to decode CSV content: {exc}") from exc

        try:
            reader = csv.reader(io.StringIO(text))
            rows = [r for r in reader if any(cell.strip() for cell in r)]
        except Exception as exc:
            raise ParseError(f"Failed to parse CSV rows: {exc}") from exc

        if not rows:
            return ParsedDocument(title=Path(filename).stem or filename, blocks=[])

        headers = [c.strip() for c in rows[0]]
        data_rows = rows[1:]

        blocks: list[Block] = []
        for r in data_rows:
            # Pair each column header with cell value
            parts: list[str] = []
            for h, val in zip(headers, r):
                v_clean = val.strip()
                parts.append(f"{h}: {v_clean}")
            row_text = ", ".join(parts)
            blocks.append(
                Block(
                    kind="row",
                    text=row_text,
                    heading_path=(),
                    page=None,
                )
            )

        title = Path(filename).stem or filename
        return ParsedDocument(title=title, blocks=blocks)
