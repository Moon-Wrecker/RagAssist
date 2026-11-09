"""Rerank node reordering candidate document passages."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState
from ragassist.platform.rerank.ports import Candidate


def make_rerank_node(reranker: Any):  # type: ignore[no-untyped-def]
    async def rerank(state: AssistantState) -> dict[str, Any]:
        query = state.get("current_query") or state.get("question", "")
        chunks = state.get("retrieved_chunks", [])
        if not chunks:
            return {"reranked_chunks": []}

        candidates = [
            Candidate(chunk_id=c.chunk_id, text=c.text, score=getattr(c, "score", 0.0))
            for c in chunks
        ]
        result = await reranker.rerank(query, candidates, top_n=min(len(chunks), 4))
        scored = getattr(result, "items", result)  # the chain returns a ChainResult, a bare reranker a list

        scored_map = {s.chunk_id: s.score for s in scored}
        reranked = [c for c in chunks if c.chunk_id in scored_map]
        reranked.sort(key=lambda c: scored_map.get(c.chunk_id, 0.0), reverse=True)
        if not reranked:
            reranked = list(chunks)

        return {"reranked_chunks": reranked}

    return rerank
