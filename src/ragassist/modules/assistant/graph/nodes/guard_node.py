"""Guard input node evaluating prompt injections and adversarial inputs."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState
from ragassist.platform.decisions.service import DecisionService


def make_guard_node(decision_service: DecisionService):  # type: ignore[no-untyped-def]
    async def guard_input(state: AssistantState) -> dict[str, Any]:
        question = state.get("question", "")
        verdict = await decision_service.check_safety(question)
        is_safe = verdict.is_safe

        updates: dict[str, Any] = {
            "is_safe": is_safe,
            "decider_used": verdict.provider_used,
        }
        if not is_safe:
            if "safety_check_error" in verdict.violation_categories:
                # Fail closed, but do not accuse the person: the check itself did not run.
                updates["answer"] = (
                    "I could not run the safety check just now, so I cannot answer yet. "
                    "Please try again in a moment."
                )
            else:
                updates["answer"] = (
                    "I cannot process this request because it violates safety guidelines."
                )
            updates["status"] = "blocked"
            updates["escalated"] = False
            updates["citations"] = []
            updates["tool_calls"] = []
        return updates

    return guard_input


def route_after_guard(state: AssistantState) -> str:
    """Route to router if safe; otherwise finalize immediately."""
    if not state.get("is_safe", True):
        return "finalize"
    return "router"
