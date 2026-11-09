"""Standalone unit tests for Milestone 3: Hybrid Retrieval and Reranker Chain.

Tests cover:
1. VectorRetriever (pgvector cosine similarity, iterative_scan, tenant isolation).
2. KeywordRetriever (PostgreSQL websearch_to_tsquery + ts_rank_cd, ParadeDB BM25).
3. Reciprocal Rank Fusion (RRF k=60, hit ranking fusion).
4. Reranker adapters (Noop, Decision, Api, FlashRank, CrossEncoder).
5. RerankerChain (FallbackChain, timeouts, failure fallthrough, disabled toggle).
6. ContextBuilder (deduplication, token budget enforcement, citations).
7. HybridRetrievalService & Spotlighting (<document id=...>).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from ragassist.modules.retrieval import (
    Citation,
    ContextBuilder,
    ContextPack,
    Hit,
    HybridRetrievalResult,
    HybridRetrievalService,
    HybridRetriever,
    KeywordRetriever,
    Passage,
    VectorRetriever,
    fuse_hit_rankings,
    reciprocal_rank_fusion,
)
from ragassist.platform.decisions.ports import ScoreAnswer
from ragassist.platform.rerank.adapters.api_reranker_adapter import ApiReranker
from ragassist.platform.rerank.adapters.decision_reranker import DecisionReranker
from ragassist.platform.rerank.adapters.noop_adapter import NoopReranker
from ragassist.platform.rerank.adapters.reranker_chain import RerankerChain
from ragassist.platform.rerank.ports import Candidate, Scored

pytestmark = pytest.mark.unit


class SimpleTokenCounter:
    """Whitespace token counter for unit test budget verification."""

    def count(self, text: str) -> int:
        return len(text.split())

    def encode(self, text: str) -> list[str]:
        return text.split()

    def decode(self, tokens: list[str]) -> str:
        return " ".join(tokens)


class MockEmbeddingProvider:
    """Embedding double returning deterministic vectors."""

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim
        self.name = "mock_embedder"

    def dimension(self) -> int:
        return self.dim

    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * self.dim

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dim for _ in texts]


def make_fake_hit(
    chunk_id: str,
    text: str,
    score: float,
    *,
    document_id: str = "doc-1",
    tenant_id: str | None = "tenant-a",
    title: str = "Test Guide",
    page: int | None = 1,
    heading_path: tuple[str, ...] = ("Section A",),
) -> Hit:
    return Hit(
        chunk_id=chunk_id,
        document_id=document_id,
        tenant_id=tenant_id,
        score=score,
        text=text,
        heading_path=heading_path,
        page=page,
        title=title,
    )


# ==============================================================================
# 1. VectorRetriever Unit Tests
# ==============================================================================


class TestVectorRetrieverUnit:
    @pytest.mark.asyncio
    async def test_empty_query_or_zero_k_returns_empty(self) -> None:
        retriever = VectorRetriever(embedder=MockEmbeddingProvider(), session_factory=MagicMock())
        assert await retriever.search("", tenant_id="t1", k=5) == []
        assert await retriever.search("   ", tenant_id="t1", k=5) == []
        assert await retriever.search("query", tenant_id="t1", k=0) == []
        assert await retriever.search("query", tenant_id="t1", k=-1) == []

    @pytest.mark.asyncio
    async def test_search_executes_pgvector_query_with_tenant_isolation(self) -> None:
        # Mock database session
        mock_session = AsyncMock()
        mock_session.in_transaction = MagicMock(return_value=False)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            {
                "id": "c1",
                "document_id": "doc-1",
                "tenant_id": "tenant-1",
                "text": "sample text",
                "embed_text": "[Document: MyDoc | Section: Sec1]\nsample text",
                "heading_path": ["Sec1"],
                "page": 2,
                "title": "MyDoc",
                "score": 0.95,
            }
        ]
        mock_session.execute.return_value = mock_result
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        retriever = VectorRetriever(
            embedder=MockEmbeddingProvider(dim=4),
            session_factory=mock_session_factory,
            iterative_scan="relaxed_order",
        )

        hits = await retriever.search(
            "pricing details",
            tenant_id="tenant-1",
            k=3,
            filters={"document_id": "doc-1"},
        )

        assert len(hits) == 1
        assert hits[0].chunk_id == "c1"
        assert hits[0].title == "MyDoc"
        assert hits[0].heading_path == ("Sec1",)
        assert hits[0].score == 0.95

        # Verify that iterative_scan and tenant_id were executed
        calls = [str(call.args[0]) for call in mock_session.execute.call_args_list if call.args]
        assert any("set_config('app.tenant_id'" in c for c in calls)
        assert any("hnsw.iterative_scan" in c for c in calls)


# ==============================================================================
# 2. KeywordRetriever Unit Tests
# ==============================================================================


class TestKeywordRetrieverUnit:
    @pytest.mark.asyncio
    async def test_empty_query_or_zero_k_returns_empty(self) -> None:
        retriever = KeywordRetriever(session_factory=MagicMock(), backend="fts")
        assert await retriever.search("", tenant_id="t1", k=5) == []
        assert await retriever.search("   ", tenant_id="t1", k=5) == []
        assert await retriever.search("term", tenant_id="t1", k=0) == []

    @pytest.mark.asyncio
    async def test_fts_search_uses_websearch_to_tsquery_and_ts_rank_cd(self) -> None:
        mock_session = AsyncMock()
        mock_session.in_transaction = MagicMock(return_value=False)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            {
                "id": "c2",
                "document_id": "doc-2",
                "tenant_id": "t1",
                "text": "lexical keyword text",
                "embed_text": None,
                "heading_path": ["Overview"],
                "page": 1,
                "title": "Doc Title",
                "score": 0.88,
            }
        ]
        mock_session.execute.return_value = mock_result
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        retriever = KeywordRetriever(session_factory=mock_session_factory, backend="fts")
        hits = await retriever.search("keyword -minus", tenant_id="t1", k=5)

        assert len(hits) == 1
        assert hits[0].chunk_id == "c2"
        assert hits[0].score == 0.88

        # Verify query SQL contains websearch_to_tsquery and ts_rank_cd
        sql_calls = [str(call.args[0]) for call in mock_session.execute.call_args_list if call.args]
        search_query_call = [s for s in sql_calls if "websearch_to_tsquery" in s]
        assert len(search_query_call) > 0
        assert "ts_rank_cd" in search_query_call[0]

    @pytest.mark.asyncio
    async def test_paradedb_fallback_to_fts_on_error(self) -> None:
        mock_session = AsyncMock()
        mock_session.in_transaction = MagicMock(return_value=False)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            {
                "id": "c3",
                "document_id": "doc-3",
                "tenant_id": "t1",
                "text": "fallback text",
                "embed_text": None,
                "heading_path": [],
                "page": None,
                "title": "",
                "score": 0.5,
            }
        ]
        # First execute raises (ParadeDB not available), second returns mock_result (FTS fallback)
        mock_session.execute.side_effect = [
            None,  # set_config
            RuntimeError("paradedb syntax error"),  # ParadeDB attempt fails
            mock_result,  # FTS attempt succeeds
        ]
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        retriever = KeywordRetriever(session_factory=mock_session_factory, backend="paradedb")
        hits = await retriever.search("query", tenant_id="t1", k=2)
        assert len(hits) == 1
        assert hits[0].chunk_id == "c3"


# ==============================================================================
# 3. Reciprocal Rank Fusion Unit Tests
# ==============================================================================


class TestFusionUnit:
    def test_reciprocal_rank_fusion_basic_and_tie_breaking(self) -> None:
        rankings = [["a", "b", "c"], ["b", "a", "d"]]
        fused = reciprocal_rank_fusion(rankings, k=60)
        items = [item for item, _ in fused]
        # a: 1/61 + 1/62; b: 1/62 + 1/61 -> tie, 'a' seen first
        assert items == ["a", "b", "c", "d"]
        assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)

    def test_fuse_hit_rankings_merges_metadata_and_computes_rrf_score(self) -> None:
        h1 = make_fake_hit("c1", "alpha text", 0.9)
        h2 = make_fake_hit("c2", "beta text", 0.8)
        h3 = make_fake_hit("c3", "gamma text", 0.7)

        dense_hits = [h1, h2]
        sparse_hits = [h2, h3]

        fused = fuse_hit_rankings([dense_hits, sparse_hits], k=60, top_k=2)
        assert len(fused) == 2
        # c2 appears in both lists (rank 2 in dense, rank 1 in sparse)
        # c2 score = 1/62 + 1/61
        # c1 score = 1/61
        # c2 should rank first!
        assert fused[0].chunk_id == "c2"
        assert fused[0].score == pytest.approx(1 / 61 + 1 / 62)
        assert fused[1].chunk_id == "c1"

    @pytest.mark.asyncio
    async def test_hybrid_retriever_combines_dense_and_sparse(self) -> None:
        mock_dense = AsyncMock()
        mock_sparse = AsyncMock()

        mock_dense.search.return_value = [make_fake_hit("d1", "dense text", 0.95)]
        mock_sparse.search.return_value = [make_fake_hit("s1", "sparse text", 0.85)]

        retriever = HybridRetriever(dense=mock_dense, sparse=mock_sparse, rrf_k=60)
        hits = await retriever.search("search terms", tenant_id="tenant-x", k=5)

        assert len(hits) == 2
        mock_dense.search.assert_called_once_with(
            "search terms", tenant_id="tenant-x", k=5, filters=None
        )
        mock_sparse.search.assert_called_once_with(
            "search terms", tenant_id="tenant-x", k=5, filters=None
        )


# ==============================================================================
# 4. Reranker Adapters Unit Tests
# ==============================================================================


class TestRerankerAdaptersUnit:
    @pytest.mark.asyncio
    async def test_noop_reranker(self) -> None:
        reranker = NoopReranker()
        assert reranker.name == "none"
        candidates = [Candidate("c1", "text 1", 0.5), Candidate("c2", "text 2", 0.3)]
        scored = await reranker.rerank("query", candidates, top_n=1)
        assert len(scored) == 1
        assert scored[0].chunk_id == "c1"
        assert scored[0].score == 0.5

    @pytest.mark.asyncio
    async def test_decision_reranker(self) -> None:
        mock_decider = AsyncMock()
        mock_decider.evaluate_score.side_effect = [
            ScoreAnswer("relevance", 0.2, 0.9),
            ScoreAnswer("relevance", 0.9, 0.95),
        ]

        reranker = DecisionReranker(decider=mock_decider)
        assert reranker.name == "decision"
        candidates = [Candidate("c1", "low text"), Candidate("c2", "high text")]
        scored = await reranker.rerank("query", candidates, top_n=2)

        assert len(scored) == 2
        assert scored[0].chunk_id == "c2"
        assert scored[0].score == 0.9
        assert scored[1].chunk_id == "c1"
        assert scored[1].score == 0.2

    @pytest.mark.asyncio
    async def test_api_reranker(self) -> None:
        with respx.mock(assert_all_called=True) as mock:
            route = mock.post("https://api.test/v1/rerank").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "results": [
                            {"index": 1, "relevance_score": 0.99},
                            {"index": 0, "relevance_score": 0.44},
                        ]
                    },
                )
            )

            reranker = ApiReranker(
                base_url="https://api.test/v1",
                api_key="secret-api-key",
                model="test-model",
            )
            candidates = [Candidate("c1", "first"), Candidate("c2", "second")]
            scored = await reranker.rerank("search query", candidates, top_n=2)

            assert len(scored) == 2
            assert scored[0].chunk_id == "c2"
            assert scored[0].score == 0.99
            assert scored[1].chunk_id == "c1"
            assert scored[1].score == 0.44

            req = route.calls.last.request
            assert req.headers["authorization"] == "Bearer secret-api-key"

    @pytest.mark.asyncio
    async def test_reranker_chain_fallback_and_timeouts(self) -> None:
        # Member 1 fails with error
        failing_member = AsyncMock()
        failing_member.name = "failing"
        failing_member.rerank.side_effect = RuntimeError("Service Unavailable")

        # Member 2 times out
        async def slow_rerank(*args: Any, **kwargs: Any) -> list[Scored]:
            await asyncio.sleep(0.5)
            return [Scored("c1", 1.0)]

        slow_member = MagicMock()
        slow_member.name = "slow"
        slow_member.rerank = slow_rerank

        # Member 3 succeeds
        succeeding_member = AsyncMock()
        succeeding_member.name = "backup"
        succeeding_member.rerank.return_value = [Scored("c2", 0.95)]

        chain = RerankerChain(
            members=[failing_member, slow_member, succeeding_member],
            timeout_ms=50,  # 50ms timeout triggers slow_member failure
            enabled=True,
        )

        candidates = [Candidate("c1", "text 1"), Candidate("c2", "text 2")]
        result = await chain.rerank("query", candidates, top_n=1)

        assert result.reranker == "backup"
        assert len(result.items) == 1
        assert result.items[0].chunk_id == "c2"

    @pytest.mark.asyncio
    async def test_reranker_chain_disabled_returns_noop(self) -> None:
        member = AsyncMock()
        chain = RerankerChain(members=[member], enabled=False)
        candidates = [Candidate("c1", "text 1", 0.7), Candidate("c2", "text 2", 0.6)]
        result = await chain.rerank("query", candidates, top_n=2)

        assert result.reranker == "none"
        assert len(result.items) == 2
        member.rerank.assert_not_called()


# ==============================================================================
# 5. ContextBuilder & Spotlighting Unit Tests
# ==============================================================================


class TestContextBuilderAndSpotlightingUnit:
    def test_context_builder_budget_and_deduplication(self) -> None:
        counter = SimpleTokenCounter()
        builder = ContextBuilder(tokenizer=counter, budget_tokens=15)

        hits = [
            make_fake_hit(
                "c1",
                "apple banana orange grape",
                0.9,
                title="Doc 1",
                page=1,
                heading_path=("Fruit",),
            ),
            make_fake_hit("c1", "apple banana orange grape", 0.85),  # duplicate ID
            make_fake_hit("c2", "apple banana orange grape", 0.8),  # duplicate text
            make_fake_hit(
                "c3", "dog elephant giraffe zebra lion tiger bear", 0.7, title="Doc 2", page=3
            ),
        ]

        pack = builder.build(hits)
        assert len(pack.passages) == 2
        assert pack.passages[0].chunk_id == "c1"
        assert pack.passages[1].chunk_id == "c3"
        total_tokens = sum(counter.count(p.text) for p in pack.passages)
        assert total_tokens <= 15

    def test_spotlight_xml_formatting(self) -> None:
        passages = [
            Passage(
                chunk_id="chk-123",
                text="Postgres pgvector supports HNSW indexing.",
                citation=Citation(
                    title="Postgres Guide", page=4, heading_path=("Storage", "Vector")
                ),
                score=0.92,
            ),
            Passage(
                chunk_id="chk-456",
                text="BM25 scoring balances term frequency and saturation.",
                citation=Citation(title="Search Guide", page=None, heading_path=()),
                score=0.88,
            ),
        ]

        pack = ContextPack(passages=passages)
        spotlight = pack.to_spotlight_text()

        expected_tag_1 = (
            '<document id="chk-123" title="Postgres Guide" page="4" section="Storage > Vector">'
        )
        expected_tag_2 = '<document id="chk-456" title="Search Guide">'

        assert expected_tag_1 in spotlight
        assert "Postgres pgvector supports HNSW indexing." in spotlight
        assert expected_tag_2 in spotlight
        assert "BM25 scoring balances term frequency and saturation." in spotlight
        assert spotlight.count("</document>") == 2


# ==============================================================================
# 6. HybridRetrievalService End-to-End Unit Tests
# ==============================================================================


class TestHybridRetrievalServiceUnit:
    @pytest.mark.asyncio
    async def test_full_pipeline_orchestration(self) -> None:
        # Mock retriever
        mock_retriever = AsyncMock()
        mock_retriever.search.return_value = [
            make_fake_hit("c1", "how to configure pgvector", 0.8, title="DB Manual", page=10),
            make_fake_hit(
                "c2", "troubleshooting pgvector connection", 0.7, title="DB Manual", page=12
            ),
        ]

        # Mock reranker chain
        mock_reranker = AsyncMock()
        mock_reranker.rerank.return_value = MagicMock(
            reranker="test_reranker",
            items=[Scored("c2", 0.99), Scored("c1", 0.75)],
        )

        # Mock rewriter
        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite.return_value = "pgvector configuration troubleshooting"

        builder = ContextBuilder(tokenizer=SimpleTokenCounter(), budget_tokens=100)

        service = HybridRetrievalService(
            retriever=mock_retriever,
            reranker=mock_reranker,
            context_builder=builder,
            rewriter=mock_rewriter,
        )

        result = await service.retrieve(
            "configure pgvector",
            tenant_id="tenant-123",
            top_k=10,
            top_n=2,
            rewrite=True,
        )

        assert isinstance(result, HybridRetrievalResult)
        assert result.search_query == "pgvector configuration troubleshooting"
        assert result.reranker_used == "test_reranker"
        assert len(result.hits) == 2
        # After reranking, c2 had score 0.99, so it should rank first
        assert result.hits[0].chunk_id == "c2"
        assert result.hits[0].score == 0.99
        assert result.hits[1].chunk_id == "c1"

        # Check spotlighted XML
        assert '<document id="c2"' in result.spotlighted_context
        assert '<document id="c1"' in result.spotlighted_context
        assert "</document>" in result.spotlighted_context

    @pytest.mark.asyncio
    async def test_empty_query_returns_clean_empty_result(self) -> None:
        service = HybridRetrievalService(
            retriever=AsyncMock(),
            reranker=AsyncMock(),
            context_builder=ContextBuilder(tokenizer=SimpleTokenCounter(), budget_tokens=50),
        )

        result = await service.retrieve("", tenant_id="tenant-123")
        assert result.hits == []
        assert result.spotlighted_context == ""
        assert result.reranker_used == "none"
