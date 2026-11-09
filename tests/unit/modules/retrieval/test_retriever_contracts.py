"""The hybrid retriever runs the shared RetrieverContract over two in-memory sub-retrievers, plus the
behaviour specific to fusion: one empty side, filters and tenant passed through to both sides, and
the configured rrf_k. Vector and keyword adapters need Postgres and are in tests/integration."""

from __future__ import annotations

import uuid

import pytest
from fakes.retriever import InMemoryRetriever
from support.contracts import RetrieverContract
from support.contracts.retriever import Corpus
from support.specs import need

TENANT_A = uuid.UUID("a0000000-0000-0000-0000-00000000000a")
TENANT_B = uuid.UUID("b0000000-0000-0000-0000-00000000000b")


def seeded_pair() -> tuple[InMemoryRetriever, InMemoryRetriever]:
    """Two sub-retrievers holding the same rows, as a dense and a sparse index would."""
    rows = [
        dict(chunk_id="a1", document_id="doc-a", tenant_id=TENANT_A, text="zanzibar travel policy"),
        dict(
            chunk_id="a2", document_id="doc-a", tenant_id=TENANT_A, text="expense zanzibar receipts"
        ),
        dict(chunk_id="b1", document_id="doc-b", tenant_id=TENANT_B, text="quokka habitat notes"),
        dict(chunk_id="g1", document_id="doc-g", tenant_id=None, text="world geography reference"),
    ]
    dense, sparse = InMemoryRetriever(), InMemoryRetriever()
    for row in rows:
        dense.add(**row)
        sparse.add(**row)
    return dense, sparse


class TestHybridRetrieverContract(RetrieverContract):
    @pytest.fixture
    def corpus(self) -> Corpus:
        dense, sparse = seeded_pair()
        retriever = need("retrieval.HybridRetriever")(dense=dense, sparse=sparse, rrf_k=60)
        return Corpus(retriever, TENANT_A, TENANT_B, "doc-a", "doc-b")


class TestFusionBehaviour:
    async def test_an_empty_sparse_side_does_not_hide_the_dense_hits(self) -> None:
        dense, _ = seeded_pair()
        retriever = need("retrieval.HybridRetriever")(
            dense=dense, sparse=InMemoryRetriever(), rrf_k=60
        )
        hits = await retriever.search("zanzibar", tenant_id=TENANT_A, k=5)
        assert {hit.chunk_id for hit in hits} == {"a1", "a2"}

    async def test_an_empty_dense_side_does_not_hide_the_sparse_hits(self) -> None:
        _, sparse = seeded_pair()
        retriever = need("retrieval.HybridRetriever")(
            dense=InMemoryRetriever(), sparse=sparse, rrf_k=60
        )
        hits = await retriever.search("zanzibar", tenant_id=TENANT_A, k=5)
        assert {hit.chunk_id for hit in hits} == {"a1", "a2"}

    async def test_both_sides_empty_gives_no_hits(self) -> None:
        retriever = need("retrieval.HybridRetriever")(
            dense=InMemoryRetriever(), sparse=InMemoryRetriever(), rrf_k=60
        )
        assert await retriever.search("anything", tenant_id=TENANT_A, k=5) == []

    async def test_the_tenant_is_passed_to_both_sides(self) -> None:
        dense, sparse = seeded_pair()
        retriever = need("retrieval.HybridRetriever")(dense=dense, sparse=sparse, rrf_k=60)
        await retriever.search("zanzibar", tenant_id=TENANT_A, k=5)
        assert dense.calls[-1]["tenant_id"] == str(TENANT_A)
        assert sparse.calls[-1]["tenant_id"] == str(TENANT_A)

    async def test_filters_are_passed_to_both_sides(self) -> None:
        dense, sparse = seeded_pair()
        retriever = need("retrieval.HybridRetriever")(dense=dense, sparse=sparse, rrf_k=60)
        await retriever.search(
            "zanzibar", tenant_id=TENANT_A, k=5, filters={"document_id": "doc-a"}
        )
        assert dense.calls[-1]["filters"] == {"document_id": "doc-a"}
        assert sparse.calls[-1]["filters"] == {"document_id": "doc-a"}

    async def test_a_chunk_found_by_both_sides_ranks_above_one_found_by_one(self) -> None:
        dense, sparse = seeded_pair()
        retriever = need("retrieval.HybridRetriever")(dense=dense, sparse=sparse, rrf_k=60)
        hits = await retriever.search("zanzibar receipts", tenant_id=TENANT_A, k=5)
        assert hits[0].chunk_id == "a2"

    async def test_k_is_applied_to_the_fused_list(self) -> None:
        dense, sparse = seeded_pair()
        retriever = need("retrieval.HybridRetriever")(dense=dense, sparse=sparse, rrf_k=60)
        assert len(await retriever.search("zanzibar", tenant_id=TENANT_A, k=1)) == 1

    async def test_the_configured_rrf_k_is_honoured(self) -> None:
        """A different rrf_k must change the fused scores (RETRIEVAL_RRF_K is wired through)."""
        dense_a, sparse_a = seeded_pair()
        dense_b, sparse_b = seeded_pair()
        small = need("retrieval.HybridRetriever")(dense=dense_a, sparse=sparse_a, rrf_k=1)
        large = need("retrieval.HybridRetriever")(dense=dense_b, sparse=sparse_b, rrf_k=1000)
        a = await small.search("zanzibar", tenant_id=TENANT_A, k=5)
        b = await large.search("zanzibar", tenant_id=TENANT_A, k=5)
        assert a[0].score != pytest.approx(b[0].score)
