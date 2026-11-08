"""Hybrid retrieve node performing tenant-scoped retrieval."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState


def make_hybrid_retrieve_node(retriever: Any):  # type: ignore[no-untyped-def]
    async def hybrid_retrieve(state: AssistantState) -> dict[str, Any]:
        count = state.get("retrieve_count", 0) + 1
        principal = state["principal"]
        query = state.get("current_query") or state.get("question", "")

        hits = await retriever.search(query, tenant_id=principal.tenant_id, k=6)
        return {
            "retrieve_count": count,
            "retrieved_chunks": hits,
        }

    return hybrid_retrieve
