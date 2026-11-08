"""Hybrid Search Service orchestrating retrieval, reranking, and spotlighted context building.

Goal:
    Provide an end-to-end retrieval orchestration service that coordinates query rewriting,
    dense/sparse hybrid retrieval with Reciprocal Rank Fusion, fallback reranking, and
    spotlighted ContextBuilder formatting for grounded LLM generation.

Consulted References:
    - Cormack, Clarke, and Buettcher (2009): "Reciprocal Rank Fusion Outperforms
      Condorcet and Individual Rank Learning Methods" (SIGIR).
    - Anthropic Prompt Engineering Guidelines: Spotlighted Document Context (<document id="...">)
      to defend against indirect prompt injection and maintain clear passage attribution.
    - ADR 0005: Toggleable Reranker Chain with CPU/GPU Graceful Fallback.
"""

from dataclasses import dataclass, replace
from typing import Any
import structlog
from ragassist.modules.retrieval.application import ContextBuilder
from ragassist.modules.retrieval.domain import ContextPack, Hit
from ragassist.platform.rerank.ports import Candidate

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class HybridRetrievalResult:
    """End-to-end result of the hybrid retrieval and reranking pipeline."""

    context_pack: ContextPack
    spotlighted_context: str
    hits: list[Hit]
    reranker_used: str
    original_query: str
    search_query: str


class HybridRetrievalService:
    """Service that orchestrates query rewriting, hybrid search, reranking, and context pack construction."""

    def __init__(
        self,
        retriever: Any,
        reranker: Any,
        context_builder: ContextBuilder,
        rewriter: Any | None = None,
    ) -> None:
        self.retriever = retriever
        self.reranker = reranker
        self.context_builder = context_builder
        self.rewriter = rewriter

    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: Any,
        top_k: int = 30,
        top_n: int = 6,
        filters: dict[str, Any] | None = None,
        rewrite: bool = False,
    ) -> HybridRetrievalResult:
        """Execute full hybrid retrieval, reranking, and context building pipeline."""
        search_query = query.strip()

        # Step 1: Optional Query Rewriting
        if rewrite and self.rewriter is not None and search_query:
            try:
                if hasattr(self.rewriter, "rewrite"):
                    search_query = await self.rewriter.rewrite(search_query)
                elif callable(self.rewriter):
                    search_query = await self.rewriter(search_query)
            except Exception as exc:  # noqa: BLE001
                logger.warning("hybrid_service.rewrite_failed", error=str(exc))
                search_query = query.strip()

        if not search_query or top_k <= 0:
            empty_pack = self.context_builder.build([])
            return HybridRetrievalResult(
                context_pack=empty_pack,
                spotlighted_context="",
                hits=[],
                reranker_used="none",
                original_query=query,
                search_query=search_query,
            )

        # Step 2: Hybrid Retrieval (Vector + Keyword + RRF)
        retrieved_hits = await self.retriever.search(
            search_query,
            tenant_id=tenant_id,
            k=top_k,
            filters=filters,
        )

        if not retrieved_hits or top_n <= 0:
            empty_pack = self.context_builder.build([])
            return HybridRetrievalResult(
                context_pack=empty_pack,
                spotlighted_context="",
                hits=[],
                reranker_used="none",
                original_query=query,
                search_query=search_query,
            )

        # Step 3: Reranking Chain
        candidates = [
            Candidate(chunk_id=h.chunk_id, text=h.text, score=h.score)
            for h in retrieved_hits
        ]

        reranker_used = "none"
        reranked_hits: list[Hit] = []

        if self.reranker is not None:
            try:
                chain_result = await self.reranker.rerank(
                    search_query,
                    candidates,
                    top_n=top_n,
                )
                reranker_used = getattr(chain_result, "reranker", "none")
                scored_items = getattr(chain_result, "items", chain_result)

                hit_lookup = {h.chunk_id: h for h in retrieved_hits}
                for item in scored_items:
                    if item.chunk_id in hit_lookup:
                        reranked_hits.append(
                            replace(hit_lookup[item.chunk_id], score=item.score)
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("hybrid_service.reranking_failed", error=str(exc))
                reranked_hits = retrieved_hits[:top_n]
                reranker_used = "fallback_rrf"
        else:
            reranked_hits = retrieved_hits[:top_n]

        # Step 4: Context Building & Spotlighting
        context_pack = self.context_builder.build(reranked_hits)
        spotlighted = context_pack.to_spotlight_text()

        return HybridRetrievalResult(
            context_pack=context_pack,
            spotlighted_context=spotlighted,
            hits=reranked_hits,
            reranker_used=reranker_used,
            original_query=query,
            search_query=search_query,
        )


__all__ = [
    "ContextBuilder",
    "ContextPack",
    "Hit",
    "HybridRetrievalResult",
    "HybridRetrievalService",
]
