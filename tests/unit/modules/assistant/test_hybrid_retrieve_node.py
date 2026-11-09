"""The retrieve node returns the retriever's hits unchanged and summarises them for the trace."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from ragassist.modules.assistant.graph.nodes.hybrid_retrieve_node import (
    _TRACE_TEXT_CHARS,
    _hit_summary,
    make_hybrid_retrieve_node,
)


@dataclass
class Hit:
    chunk_id: str
    text: str
    score: float


class Retriever:
    def __init__(self, hits: list[Hit]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, object, int]] = []

    async def search(self, query: str, tenant_id: object = None, k: int = 6) -> list[Hit]:
        self.calls.append((query, tenant_id, k))
        return self.hits


@pytest.mark.asyncio
async def test_the_node_passes_hits_through_and_counts_attempts() -> None:
    hits = [Hit("c1", "refunds take five days", 0.91234567)]
    retriever = Retriever(hits)
    node = make_hybrid_retrieve_node(retriever)
    state = {
        "principal": SimpleNamespace(tenant_id="tenant-a"),
        "question": "how long do refunds take?",
        "retrieve_count": 1,
    }
    out = await node(state)  # type: ignore[arg-type]
    assert out == {"retrieve_count": 2, "retrieved_chunks": hits}
    assert retriever.calls == [("how long do refunds take?", "tenant-a", 6)]


def test_the_trace_summary_is_bounded_and_rounded() -> None:
    summary = _hit_summary(Hit("c1", "x" * (_TRACE_TEXT_CHARS + 50), 0.912345678))
    assert summary["chunk_id"] == "c1"
    assert summary["score"] == 0.9123
    assert len(summary["text"]) == _TRACE_TEXT_CHARS
