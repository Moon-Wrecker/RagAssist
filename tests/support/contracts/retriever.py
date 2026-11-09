"""Contract for ``Retriever`` ports (vector, keyword, hybrid, and the in-memory test double).

Subclasses provide a ``corpus`` fixture returning a :class:`Corpus`: a retriever seeded with one
tenant-A document containing the word ``zanzibar``, one tenant-B document containing ``quokka``, and
one global document (tenant ``None``) containing ``geography``. The contract is about behaviour, not
scoring, so it only asserts ordering and membership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest


@dataclass
class Corpus:
    retriever: Any
    tenant_a: Any
    tenant_b: Any
    a_document_id: str
    b_document_id: str


class RetrieverContract:
    @pytest.fixture
    def corpus(self) -> Corpus:  # pragma: no cover - overridden
        raise NotImplementedError

    async def test_hits_expose_the_documented_fields(self, corpus: Corpus) -> None:
        hits = await corpus.retriever.search("zanzibar", tenant_id=corpus.tenant_a, k=5)
        assert hits
        for hit in hits:
            for field_name in ("chunk_id", "document_id", "score", "text", "heading_path"):
                assert hasattr(hit, field_name), f"hit lacks {field_name}"

    async def test_own_tenant_finds_its_own_document(self, corpus: Corpus) -> None:
        hits = await corpus.retriever.search("zanzibar", tenant_id=corpus.tenant_a, k=5)
        assert any("zanzibar" in hit.text for hit in hits)

    async def test_another_tenant_never_sees_the_document(self, corpus: Corpus) -> None:
        hits = await corpus.retriever.search("zanzibar", tenant_id=corpus.tenant_b, k=5)
        assert all("zanzibar" not in hit.text for hit in hits)

    async def test_global_documents_are_visible_to_every_tenant(self, corpus: Corpus) -> None:
        for tenant in (corpus.tenant_a, corpus.tenant_b):
            hits = await corpus.retriever.search("geography", tenant_id=tenant, k=5)
            assert any("geography" in hit.text for hit in hits)

    async def test_k_limits_the_number_of_hits(self, corpus: Corpus) -> None:
        hits = await corpus.retriever.search("geography", tenant_id=corpus.tenant_a, k=1)
        assert len(hits) <= 1

    async def test_scores_are_sorted_descending(self, corpus: Corpus) -> None:
        hits = await corpus.retriever.search("geography zanzibar", tenant_id=corpus.tenant_a, k=10)
        scores = [hit.score for hit in hits]
        assert scores == sorted(scores, reverse=True)

    async def test_the_same_query_gives_the_same_ids(self, corpus: Corpus) -> None:
        first = await corpus.retriever.search("geography", tenant_id=corpus.tenant_a, k=5)
        second = await corpus.retriever.search("geography", tenant_id=corpus.tenant_a, k=5)
        assert [h.chunk_id for h in first] == [h.chunk_id for h in second]

    async def test_an_empty_query_returns_no_hits(self, corpus: Corpus) -> None:
        assert await corpus.retriever.search("   ", tenant_id=corpus.tenant_a, k=5) == []

    async def test_a_zero_k_returns_no_hits(self, corpus: Corpus) -> None:
        assert await corpus.retriever.search("zanzibar", tenant_id=corpus.tenant_a, k=0) == []

    async def test_document_filter_restricts_the_hits(self, corpus: Corpus) -> None:
        hits = await corpus.retriever.search(
            "geography zanzibar",
            tenant_id=corpus.tenant_a,
            k=10,
            filters={"document_id": corpus.a_document_id},
        )
        assert hits and all(hit.document_id == corpus.a_document_id for hit in hits)
