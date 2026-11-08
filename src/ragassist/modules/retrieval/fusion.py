"""Reciprocal Rank Fusion (RRF) and Hybrid Retriever combining vector and lexical rankings."""

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from typing import Any
import structlog
from ragassist.modules.retrieval.domain import Hit, reciprocal_rank_fusion

logger = structlog.get_logger(__name__)


def fuse_hit_rankings(
    hit_lists: Sequence[Sequence[Hit]],
    *,
    k: int = 60,
    top_k: int | None = None,
) -> list[Hit]:
    """Fuse multiple ranked lists of Hit objects using Reciprocal Rank Fusion."""
    lookup: dict[str, Hit] = {}
    rankings: list[list[str]] = []

    for hits in hit_lists:
        id_list: list[str] = []
        for hit in hits:
            id_list.append(hit.chunk_id)
            if hit.chunk_id not in lookup:
                lookup[hit.chunk_id] = hit
        rankings.append(id_list)

    fused_scores = reciprocal_rank_fusion(rankings, k=k)

    fused_hits: list[Hit] = []
    for chunk_id, score in fused_scores:
        if chunk_id in lookup:
            fused_hits.append(replace(lookup[chunk_id], score=score))

    if top_k is not None:
        return fused_hits[:top_k]
    return fused_hits


class HybridRetriever:
    """Combines dense vector retrieval and sparse keyword search via RRF."""

    def __init__(
        self,
        dense: Any,
        sparse: Any,
        rrf_k: int = 60,
    ) -> None:
        self.dense = dense
        self.sparse = sparse
        self.rrf_k = rrf_k

    async def search(
        self,
        query: str,
        *,
        tenant_id: Any,
        k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]:
        """Perform parallel dense and sparse search and fuse results with RRF."""
        if k <= 0 or not query.strip():
            return []

        # Run both searches in parallel
        dense_coro = self.dense.search(query, tenant_id=tenant_id, k=k, filters=filters)
        sparse_coro = self.sparse.search(query, tenant_id=tenant_id, k=k, filters=filters)

        results = await asyncio.gather(dense_coro, sparse_coro, return_exceptions=True)

        dense_hits: list[Hit] = []
        if isinstance(results[0], list):
            dense_hits = results[0]
        elif isinstance(results[0], Exception):
            logger.warning("hybrid_retriever.dense_search_failed", error=str(results[0]))

        sparse_hits: list[Hit] = []
        if isinstance(results[1], list):
            sparse_hits = results[1]
        elif isinstance(results[1], Exception):
            logger.warning("hybrid_retriever.sparse_search_failed", error=str(results[1]))

        fused = fuse_hit_rankings([dense_hits, sparse_hits], k=self.rrf_k, top_k=k)
        return fused


__all__ = [
    "HybridRetriever",
    "fuse_hit_rankings",
    "reciprocal_rank_fusion",
]
