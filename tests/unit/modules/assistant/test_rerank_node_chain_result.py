"""The rerank node must work with the production reranker chain, which returns a ChainResult (not a list)."""

from __future__ import annotations

from types import SimpleNamespace

from ragassist.modules.assistant.graph.nodes.rerank_node import make_rerank_node
from ragassist.platform.rerank.ports import Scored


class _ChainLikeReranker:
    async def rerank(self, query, candidates, *, top_n=None):  # type: ignore[no-untyped-def]
        ranked = [Scored(chunk_id="b", score=0.9), Scored(chunk_id="a", score=0.1)]
        return SimpleNamespace(items=ranked, reranker="fake")


async def test_chain_result_is_unwrapped_and_ordered_by_score() -> None:
    chunks = [
        SimpleNamespace(chunk_id="a", text="alpha", score=0.5),
        SimpleNamespace(chunk_id="b", text="beta", score=0.4),
    ]
    node = make_rerank_node(_ChainLikeReranker())
    out = await node({"question": "q", "retrieved_chunks": chunks})
    assert [c.chunk_id for c in out["reranked_chunks"]] == ["b", "a"]
