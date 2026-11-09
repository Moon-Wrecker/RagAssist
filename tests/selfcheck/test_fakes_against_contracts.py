"""Every fake that stands in for a planned port is run against that port's contract here, so a fake
cannot drift from the behaviour the production adapter must show. These run today: they need no
product code."""

from __future__ import annotations

import uuid

import pytest
from fakes.reranker import FakeReranker
from fakes.retriever import InMemoryRetriever
from support.contracts import RerankerContract, RetrieverContract
from support.contracts.retriever import Corpus

pytestmark = pytest.mark.selfcheck


TENANT_A = uuid.UUID("a0000000-0000-0000-0000-00000000000a")
TENANT_B = uuid.UUID("b0000000-0000-0000-0000-00000000000b")


class TestInMemoryRetrieverMeetsContract(RetrieverContract):
    @pytest.fixture
    def corpus(self) -> Corpus:
        retriever = InMemoryRetriever()
        retriever.add(
            chunk_id="a1", document_id="doc-a", tenant_id=TENANT_A, text="zanzibar travel policy"
        )
        retriever.add(
            chunk_id="a2", document_id="doc-a", tenant_id=TENANT_A, text="expense zanzibar receipts"
        )
        retriever.add(
            chunk_id="b1", document_id="doc-b", tenant_id=TENANT_B, text="quokka habitat notes"
        )
        retriever.add(
            chunk_id="g1", document_id="doc-g", tenant_id=None, text="world geography reference"
        )
        return Corpus(retriever, TENANT_A, TENANT_B, "doc-a", "doc-b")


class TestFakeRerankerMeetsContract(RerankerContract):
    @pytest.fixture
    def reranker(self) -> FakeReranker:
        return FakeReranker("fake")


class TestFakeRerankerStillFailsWhenScripted:
    async def test_error_injection_raises_until_the_limit(self) -> None:
        reranker = FakeReranker("flaky", error=RuntimeError("down"), fail_times=1)
        with pytest.raises(RuntimeError):
            await reranker.rerank("q", [], top_n=1)
        assert await reranker.rerank("q", [], top_n=1) == []
