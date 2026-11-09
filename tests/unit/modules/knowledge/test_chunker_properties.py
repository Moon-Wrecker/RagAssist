"""Property-based checks of the hybrid chunker over generated documents (hypothesis).

Each property is a statement about every document, so random inputs find the edge cases that
hand-written examples miss (empty blocks, one long word, unicode, repeated words). The hybrid chunker
does not yet return ChunkDraft objects (DEFECT-34), so these run as expected failures until it does.
"""

from __future__ import annotations

import pytest
from fakes.tokens import WhitespaceCounter
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from support.knowledge_builders import block, parsed_document
from support.specs import need

pytestmark = pytest.mark.slow

COUNTER = WhitespaceCounter()
MAX = 24

words = st.from_regex(r"[a-z]{1,9}", fullmatch=True)
paragraph = st.lists(words, min_size=1, max_size=80).map(" ".join)
document_blocks = st.lists(paragraph, min_size=1, max_size=6)

_settings = settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)


def chunker():  # type: ignore[no-untyped-def]
    return need("knowledge.chunker.hybrid")(
        max_tokens=MAX, overlap_tokens=0, merge_peers=True, tokenizer=COUNTER
    )


def chunks_of(texts: list[str]):  # type: ignore[no-untyped-def]
    doc = parsed_document([block("paragraph", t, ("S",)) for t in texts])
    return chunker().chunk(doc, title=doc.title)


@_settings
@given(document_blocks)
def test_no_chunk_exceeds_the_budget(texts: list[str]) -> None:
    for chunk in chunks_of(texts):
        assert COUNTER.count(chunk.text) <= MAX


@_settings
@given(document_blocks)
def test_every_source_word_is_covered(texts: list[str]) -> None:
    covered: list[str] = []
    for chunk in chunks_of(texts):
        covered.extend(chunk.text.split())
    assert sorted(covered) == sorted(" ".join(texts).split())


@_settings
@given(document_blocks)
def test_chunking_is_deterministic(texts: list[str]) -> None:
    assert [c.text for c in chunks_of(texts)] == [c.text for c in chunks_of(texts)]


@_settings
@given(document_blocks)
def test_rechunking_a_chunk_is_idempotent(texts: list[str]) -> None:
    for chunk in chunks_of(texts):
        assert [c.text for c in chunks_of([chunk.text])] == [chunk.text]


@_settings
@given(st.lists(words, min_size=1, max_size=120))
def test_source_order_is_preserved_without_overlap(words_in_order: list[str]) -> None:
    joined = " ".join(c.text for c in chunks_of([" ".join(words_in_order)])).split()
    assert joined == words_in_order


@_settings
@given(st.lists(st.text(min_size=1, max_size=6), min_size=1, max_size=30))
def test_unicode_text_never_breaks_the_budget(pieces: list[str]) -> None:
    for chunk in chunks_of([" ".join(pieces)]):
        assert COUNTER.count(chunk.text) <= MAX
