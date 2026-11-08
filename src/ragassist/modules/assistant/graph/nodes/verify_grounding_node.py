"""Verify grounding node evaluating hallucinations against retrieved chunks."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState
from ragassist.platform.decisions.service import DecisionService


def make_verify_grounding_node(decision_service: DecisionService):  # type: ignore[no-untyped-def]
    async def verify_grounding(state: AssistantState) -> dict[str, Any]:
        route = state.get("route", "")
        chunks = state.get("graded_chunks", [])
        answer = state.get("answer", "")

        if route == "general_chat" or not chunks:
            return {
                "is_grounded": True,
                "grounding_score": 1.0,
            }

        texts = [c.text for c in chunks]
        verdict = await decision_service.judge_grounding(answer, texts)
        return {
            "is_grounded": verdict.is_grounded,
            "grounding_score": verdict.grounding_score,
            "decider_used": verdict.provider_used,
        }

    return verify_grounding


def route_after_grounding(state: AssistantState) -> str:
    """Route to finalize if grounded; regenerate once, then escalate."""
    if state.get("is_grounded", False):
        return "finalize"

    if state.get("generate_count", 0) < 2:
        return "generate"

    return "escalate"
