"""Hybrid retrieve node performing tenant-scoped retrieval."""

from __future__ import annotations

from typing import Any

from ragassist.modules.assistant.graph.state import AssistantState
from ragassist.shared.observability.tracing import get_tracing

#: Passage text kept in the trace, so a reviewer sees what the model was given without a full copy of the corpus.
_TRACE_TEXT_CHARS = 600


def _hit_summary(hit: Any) -> dict[str, Any]:
    text = getattr(hit, "text", None) or getattr(hit, "content", "") or ""
    return {
        "chunk_id": str(getattr(hit, "chunk_id", getattr(hit, "id", ""))),
        "score": round(float(getattr(hit, "score", 0.0) or 0.0), 4),
        "text": str(text)[:_TRACE_TEXT_CHARS],
    }


def make_hybrid_retrieve_node(retriever: Any):  # type: ignore[no-untyped-def]
    async def hybrid_retrieve(state: AssistantState) -> dict[str, Any]:
        count = state.get("retrieve_count", 0) + 1
        principal = state["principal"]
        query = state.get("current_query") or state.get("question", "")

        with get_tracing().observe("retrieve-passages", as_type="retriever", input=query) as span:
            hits = await retriever.search(query, tenant_id=principal.tenant_id, k=6)
            span.finish([_hit_summary(h) for h in hits], hits=str(len(hits)), attempt=str(count))
        return {
            "retrieve_count": count,
            "retrieved_chunks": hits,
        }

    return hybrid_retrieve
