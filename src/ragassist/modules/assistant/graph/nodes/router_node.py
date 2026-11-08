"""Router node classifying query intent and estimating complexity."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState
from ragassist.platform.decisions.ports import ScoreLevel, ScoreQuestion
from ragassist.platform.decisions.service import DecisionService


def make_router_node(decision_service: DecisionService):  # type: ignore[no-untyped-def]
    async def router(state: AssistantState) -> dict[str, Any]:
        question = state.get("question", "")
        routing = await decision_service.route_query(question)

        # Evaluate complexity via ScoreQuestion across decider chain
        score_q = ScoreQuestion(
            name="query_complexity",
            instructions="Rate query complexity 1-5",
            levels=[
                ScoreLevel(1, "simple"),
                ScoreLevel(3, "moderate"),
                ScoreLevel(5, "complex"),
            ],
        )
        try:
            score_ans, _ = await decision_service._execute_with_confidence(
                chain=decision_service.decider_chain,
                operation=lambda d: d.evaluate_score(question, score_q),
                min_confidence=None,
            )
            complexity = float(score_ans.score)
        except Exception:
            complexity = 2.0

        return {
            "route": routing.route,
            "complexity": complexity,
            "current_query": question,
            "rewrite_count": 0,
            "retrieve_count": 0,
            "generate_count": 0,
            "retrieved_chunks": [],
            "reranked_chunks": [],
            "graded_chunks": [],
            "citations": [],
            "tool_calls": [],
            "escalated": False,
            "decider_used": routing.provider_used,
        }

    return router


def route_after_router(state: AssistantState) -> str:
    """Route according to classified intent."""
    route = state.get("route", "rag_search")
    if route == "rag_search":
        return "rewrite"
    elif route == "saas_action":
        return "account_agent"
    elif route == "general_chat":
        return "generate"
    elif route == "human_escalation":
        return "escalate"
    return "rewrite"
