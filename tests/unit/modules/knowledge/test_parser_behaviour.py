"""Format-specific parsing behaviour that the shared contract cannot express: heading paths, table and code
structure, page numbers, script stripping and CSV row shape. Output is a ParsedDocument of Blocks."""

from __future__ import annotations

from data.samples import HTML_SAMPLE, MARKDOWN_SAMPLE, PDF_PAGES, PDF_SAMPLE, pdf_document
from support.specs import need


async def parse(key: str, content: bytes, mime: str, filename: str):  # type: ignore[no-untyped-def]
    parser = need(key)()
    return await parser.parse(content, mime=mime, filename=filename)


def find(blocks, needle: str):  # type: ignore[no-untyped-def]
    return next(block for block in blocks if needle in block.text)


class TestMarkdownStructure:
    async def test_headings_build_the_heading_path(self) -> None:
        parsed = await parse(
            "knowledge.parser.markdown", MARKDOWN_SAMPLE, "text/markdown", "guide.md"
        )
        assert find(parsed.blocks, "Invoices are issued").heading_path == (
            "Billing guide",
            "Invoices",
        )

    async def test_a_table_is_one_table_block(self) -> None:
        parsed = await parse(
            "knowledge.parser.markdown", MARKDOWN_SAMPLE, "text/markdown", "guide.md"
        )
        table = find(parsed.blocks, "enterprise")
        assert table.kind == "table" and "| pro | 490 |" in table.text

    async def test_a_code_fence_is_one_code_block_with_its_body(self) -> None:
        parsed = await parse(
            "knowledge.parser.markdown", MARKDOWN_SAMPLE, "text/markdown", "guide.md"
        )
        code = find(parsed.blocks, "def total")
        assert code.kind == "code" and "return sum(items)" in code.text

    async def test_markdown_has_no_page_numbers(self) -> None:
        parsed = await parse(
            "knowledge.parser.markdown", MARKDOWN_SAMPLE, "text/markdown", "guide.md"
        )
        assert all(block.page is None for block in parsed.blocks)

    async def test_a_heading_only_document_is_not_lost(self) -> None:
        parsed = await parse(
            "knowledge.parser.markdown", b"# Only a heading\n", "text/markdown", "h.md"
        )
        assert any("Only a heading" in block.text for block in parsed.blocks)


class TestHtmlStructure:
    async def test_script_content_is_dropped(self) -> None:
        parsed = await parse("knowledge.parser.html", HTML_SAMPLE, "text/html", "guide.html")
        assert all("alert(" not in block.text for block in parsed.blocks)

    async def test_heading_levels_build_the_heading_path(self) -> None:
        parsed = await parse("knowledge.parser.html", HTML_SAMPLE, "text/html", "guide.html")
        assert find(parsed.blocks, "issued monthly").heading_path == ("Billing guide", "Invoices")

    async def test_a_table_keeps_its_cell_values(self) -> None:
        parsed = await parse("knowledge.parser.html", HTML_SAMPLE, "text/html", "guide.html")
        table = next(block for block in parsed.blocks if block.kind == "table")
        assert "pro" in table.text and "490" in table.text


class TestPdfPages:
    async def test_each_page_gets_its_page_number(self) -> None:
        parsed = await parse("knowledge.parser.pymupdf", PDF_SAMPLE, "application/pdf", "guide.pdf")
        assert find(parsed.blocks, "page one").page == 1
        assert find(parsed.blocks, "page two").page == 2

    async def test_every_page_is_kept(self) -> None:
        parsed = await parse(
            "knowledge.parser.pymupdf", pdf_document(PDF_PAGES * 3), "application/pdf", "g.pdf"
        )
        assert {1, 2}.issubset({block.page for block in parsed.blocks}) and len(parsed.blocks) >= 6

    async def test_a_single_page_document_has_page_one(self) -> None:
        parsed = await parse(
            "knowledge.parser.pymupdf", pdf_document(["Only page."]), "application/pdf", "s.pdf"
        )
        assert all(block.page == 1 for block in parsed.blocks)


class TestCsvRows:
    async def test_each_row_is_a_row_block_that_repeats_the_header(self) -> None:
        parsed = await parse(
            "knowledge.parser.tabular",
            b"plan,price\npro,490\nenterprise,2400\n",
            "text/csv",
            "p.csv",
        )
        rows = [block for block in parsed.blocks if block.kind == "row"]
        assert len(rows) == 2 and all("plan" in row.text and "price" in row.text for row in rows)

    async def test_a_quoted_comma_stays_inside_one_cell(self) -> None:
        parsed = await parse(
            "knowledge.parser.tabular", b'plan,note\npro,"a, b"\n', "text/csv", "q.csv"
        )
        assert any("a, b" in block.text for block in parsed.blocks)

    async def test_a_header_only_file_has_no_rows(self) -> None:
        parsed = await parse("knowledge.parser.tabular", b"plan,price\n", "text/csv", "h.csv")
        assert [block for block in parsed.blocks if block.kind == "row"] == []

    async def test_crlf_line_endings_are_handled(self) -> None:
        parsed = await parse(
            "knowledge.parser.tabular", b"plan,price\r\npro,490\r\n", "text/csv", "crlf.csv"
        )
        assert any("490" in block.text for block in parsed.blocks)
