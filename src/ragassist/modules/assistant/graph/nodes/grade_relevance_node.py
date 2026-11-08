"""Grade relevance node filtering retrieved passages by relevance."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState
from ragassist.platform.decisions.service import DecisionService


def make_grade_relevance_node(decision_service: DecisionService):  # type: ignore[no-untyped-def]
    async def grade_relevance(state: AssistantState) -> dict[str, Any]:
        query = state.get("current_query") or state.get("question", "")
        chunks = state.get("reranked_chunks", [])
        relevant: list[Any] = []

        for c in chunks:
            res = await decision_service.grade_chunk_relevance(query, c.text)
            if res.is_relevant:
                relevant.append(c)

        return {"graded_chunks": relevant}

    return grade_relevance


def route_after_grade(state: AssistantState) -> str:
    """Route to generate if relevant chunks exist; otherwise retry or escalate."""
    graded = state.get("graded_chunks", [])
    if graded:
        return "generate"

    rewrite_cnt = state.get("rewrite_count", 0)
    retrieve_cnt = state.get("retrieve_count", 0)

    if rewrite_cnt < 2:
        return "rewrite"
    if retrieve_cnt < 3:
        return "hybrid_retrieve"
    return "escalate"
