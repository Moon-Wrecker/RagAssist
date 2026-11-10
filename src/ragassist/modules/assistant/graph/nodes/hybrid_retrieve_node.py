"""Hybrid retrieve node performing tenant-scoped retrieval."""

from __future__ import annotations

from typing import Any

from ragassist.modules.assistant.graph.state import AssistantState
from ragassist.modules.retrieval.application.cache import RetrievalResultCache
from ragassist.shared.observability.tracing import get_tracing

#: Passages asked of the retriever for every query.
_TOP_K = 6

#: Passage text kept in the trace, so a reviewer sees what the model was given without a full copy of the corpus.
_TRACE_TEXT_CHARS = 600


def _hit_summary(hit: Any) -> dict[str, Any]:
    text = getattr(hit, "text", None) or getattr(hit, "content", "") or ""
    return {
        "chunk_id": str(getattr(hit, "chunk_id", getattr(hit, "id", ""))),
        "score": round(float(getattr(hit, "score", 0.0) or 0.0), 4),
        "text": str(text)[:_TRACE_TEXT_CHARS],
    }


def make_hybrid_retrieve_node(  # type: ignore[no-untyped-def]
    retriever: Any, cache: RetrievalResultCache | None = None
):
    async def hybrid_retrieve(state: AssistantState) -> dict[str, Any]:
        count = state.get("retrieve_count", 0) + 1
        principal = state["principal"]
        query = state.get("current_query") or state.get("question", "")

        with get_tracing().observe("retrieve-passages", as_type="retriever", input=query) as span:
            lookup = None
            if cache is not None and cache.enabled:
                role = str(getattr(principal.role, "value", principal.role))
                lookup = await cache.lookup(principal.tenant_id, role, query, _TOP_K)
            cache_hit = lookup is not None and lookup.hit
            if lookup is not None and lookup.hits is not None:
                hits = lookup.hits
            elif lookup is not None:
                complete = True
                if hasattr(retriever, "search_with_status"):
                    hits, complete = await retriever.search_with_status(
                        query, tenant_id=principal.tenant_id, k=_TOP_K
                    )
                else:
                    hits = await retriever.search(query, tenant_id=principal.tenant_id, k=_TOP_K)
                if complete and cache is not None:  # a result missing one retriever is served once, never kept
                    await cache.store(lookup, hits)
            else:
                hits = await retriever.search(query, tenant_id=principal.tenant_id, k=_TOP_K)
            span.finish(
                [_hit_summary(h) for h in hits],
                hits=str(len(hits)),
                attempt=str(count),
                cache_hit=str(cache_hit).lower(),
            )
        return {
            "retrieve_count": count,
            "retrieved_chunks": hits,
        }

    return hybrid_retrieve
