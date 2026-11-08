"""Every document parser runs the shared ParserContract (the Parser port; ADR 0003 pipeline).

A parser whose library is not installed, or whose class is not written yet, is skipped as PENDING.
"""

from __future__ import annotations

import pytest
from data.samples import CORRUPT_PDF, CSV_SAMPLE, HTML_SAMPLE, MARKDOWN_SAMPLE, PDF_SAMPLE
from support.contracts import ParserContract
from support.specs import need


class TestMarkdownParserContract(ParserContract):
    mimes = ("text/markdown",)
    sample = MARKDOWN_SAMPLE
    sample_filename = "guide.md"

    @pytest.fixture
    def parser(self):  # type: ignore[no-untyped-def]
        return need("knowledge.parser.markdown")()


class TestHtmlParserContract(ParserContract):
    mimes = ("text/html",)
    sample = HTML_SAMPLE
    sample_filename = "guide.html"

    @pytest.fixture
    def parser(self):  # type: ignore[no-untyped-def]
        return need("knowledge.parser.html")()


class TestPyMuPDFParserContract(ParserContract):
    mimes = ("application/pdf",)
    sample = PDF_SAMPLE
    corrupt = CORRUPT_PDF
    unicode_in_sample = False
    sample_filename = "guide.pdf"

    @pytest.fixture
    def parser(self):  # type: ignore[no-untyped-def]
        return need("knowledge.parser.pymupdf")()


class TestTabularParserContract(ParserContract):
    mimes = ("text/csv",)
    sample = CSV_SAMPLE
    sample_filename = "plans.csv"

    @pytest.fixture
    def parser(self):  # type: ignore[no-untyped-def]
        return need("knowledge.parser.tabular")()


class TestDoclingParserContract(ParserContract):
    """v2 adapter: runs only once the docling extra is installed (pending until then)."""

    mimes = ("application/pdf",)
    sample = PDF_SAMPLE
    corrupt = CORRUPT_PDF
    unicode_in_sample = False
    sample_filename = "guide.pdf"

    @pytest.fixture
    def parser(self):  # type: ignore[no-untyped-def]
        return need("knowledge.parser.docling")()
