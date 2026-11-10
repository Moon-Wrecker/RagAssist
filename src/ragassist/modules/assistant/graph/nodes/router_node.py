"""Router node classifying query intent and estimating complexity."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState
from ragassist.modules.assistant.graph.verdict_cache import VerdictCache
from ragassist.platform.decisions.ports import RoutingDecision, ScoreLevel, ScoreQuestion
from ragassist.platform.decisions.service import DecisionService
from ragassist.shared.observability.tracing import get_tracing

_DEFAULT_COMPLEXITY = 2.0


async def _classify(
    decision_service: DecisionService, question: str
) -> tuple[RoutingDecision, float, float | None]:
    """The route, the complexity used, and the complexity only when the scorer really answered."""
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
        measured = float(score_ans.score)
        return routing, measured, measured
    except Exception:
        return routing, _DEFAULT_COMPLEXITY, None


def make_router_node(  # type: ignore[no-untyped-def]
    decision_service: DecisionService, verdicts: VerdictCache | None = None
):
    async def router(state: AssistantState) -> dict[str, Any]:
        question = state.get("question", "")
        principal = state.get("principal")
        with get_tracing().observe("route-question", as_type="chain", input=question) as span:
            cached = await verdicts.get_route(principal, question) if verdicts else None
            if cached is not None:
                routing, complexity = cached.routing, cached.complexity
            else:
                routing, complexity, measured = await _classify(decision_service, question)
                if verdicts is not None:  # only real answers are kept: a default route is not a classification
                    await verdicts.put_route(principal, question, routing, measured)
            span.finish(
                {"route": routing.route, "complexity": complexity},
                decider=routing.provider_used,
                cache_hit=str(cached is not None).lower(),
            )

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
