"""Contract for ``Chunker`` adapters (ADR 0003; the Chunker port in knowledge/domain).

The port: ``chunk(parsed: ParsedDocument, *, title: str) -> list[ChunkDraft]`` (synchronous). A ChunkDraft
has ``text`` (raw, used for citations), ``embed_text`` (context-prefixed, used for embedding),
``heading_path``, ``page``, ``parent`` (index of the parent chunk in the returned list, or None) and
``token_count``.

Subclasses provide ``chunker`` (built with ``max_tokens=MAX_TOKENS``) and the ``counter`` fixture.
"""

from __future__ import annotations

import re

import pytest
from fakes.tokens import WhitespaceCounter

from support.knowledge_builders import block, parsed_document

MAX_TOKENS = 40


def sample_document():  # type: ignore[no-untyped-def]
    return parsed_document(
        [
            block("heading", "Invoices", ("Invoices",)),
            block(
                "paragraph",
                "Invoices are issued on the first day of each month. " * 3,
                ("Invoices",),
                1,
            ),
            block("paragraph", "Payments are due within thirty days of issue.", ("Invoices",), 1),
            block(
                "table",
                "| plan | price |\n|---|---|\n| pro | 490 |\n| enterprise | 2400 |",
                ("Invoices", "Prices"),
                2,
            ),
            block("code", "def total(items):\n    return sum(items)", ("Invoices", "Examples"), 2),
        ],
        title="Billing guide",
    )


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _collapse(text: str) -> str:
    return re.sub(r"\s+", "", text)


class ChunkerContract:
    @pytest.fixture
    def chunker(self):  # type: ignore[no-untyped-def]  # pragma: no cover - overridden
        raise NotImplementedError

    @pytest.fixture
    def counter(self):  # type: ignore[no-untyped-def]
        return WhitespaceCounter()

    def test_chunks_a_document_into_at_least_one_chunk(self, chunker) -> None:  # type: ignore[no-untyped-def]
        parsed = sample_document()
        assert len(chunker.chunk(parsed, title=parsed.title)) >= 1

    def test_an_empty_document_gives_no_chunks(self, chunker) -> None:  # type: ignore[no-untyped-def]
        assert chunker.chunk(parsed_document([], title="empty"), title="empty") == []

    def test_no_chunk_exceeds_the_token_budget(self, chunker, counter) -> None:  # type: ignore[no-untyped-def]
        parsed = sample_document()
        for chunk in chunker.chunk(parsed, title=parsed.title):
            assert counter.count(chunk.text) <= MAX_TOKENS, chunk.text

    def test_chunk_text_is_verbatim_source_text(self, chunker) -> None:  # type: ignore[no-untyped-def]
        parsed = sample_document()
        source = _collapse(" ".join(b.text for b in parsed.blocks))
        for chunk in chunker.chunk(parsed, title=parsed.title):
            assert _collapse(chunk.text) in source

    def test_every_source_word_is_covered_by_some_chunk(self, chunker) -> None:  # type: ignore[no-untyped-def]
        parsed = sample_document()
        source_words = _words(" ".join(b.text for b in parsed.blocks))
        covered: set[str] = set()
        for chunk in chunker.chunk(parsed, title=parsed.title):
            covered |= _words(chunk.text)
        assert source_words <= covered, source_words - covered

    def test_embedded_text_contains_the_raw_text(self, chunker) -> None:  # type: ignore[no-untyped-def]
        parsed = sample_document()
        for chunk in chunker.chunk(parsed, title=parsed.title):
            assert chunk.text in chunk.embed_text

    def test_embedded_text_carries_the_title_and_section(self, chunker) -> None:  # type: ignore[no-untyped-def]
        parsed = sample_document()
        first = next(c for c in chunker.chunk(parsed, title=parsed.title) if "issued" in c.text)
        assert "Billing guide" in first.embed_text and "Invoices" in first.embed_text

    def test_heading_path_is_kept_on_chunks(self, chunker) -> None:  # type: ignore[no-untyped-def]
        parsed = sample_document()
        chunks = chunker.chunk(parsed, title=parsed.title)
        assert any(tuple(chunk.heading_path)[:1] == ("Invoices",) for chunk in chunks)

    def test_chunking_is_deterministic(self, chunker) -> None:  # type: ignore[no-untyped-def]
        parsed = sample_document()
        first = [c.text for c in chunker.chunk(parsed, title=parsed.title)]
        second = [c.text for c in chunker.chunk(parsed, title=parsed.title)]
        assert first == second

    def test_parent_references_point_at_earlier_chunks(self, chunker) -> None:  # type: ignore[no-untyped-def]
        parsed = sample_document()
        chunks = chunker.chunk(parsed, title=parsed.title)
        for index, chunk in enumerate(chunks):
            if chunk.parent is not None:
                assert 0 <= chunk.parent < len(chunks) and chunk.parent != index
