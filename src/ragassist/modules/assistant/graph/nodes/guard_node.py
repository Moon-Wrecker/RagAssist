"""Guard input node evaluating prompt injections and adversarial inputs."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState
from ragassist.modules.assistant.graph.verdict_cache import VerdictCache
from ragassist.platform.decisions.service import DecisionService
from ragassist.shared.observability.tracing import get_tracing


def make_guard_node(  # type: ignore[no-untyped-def]
    decision_service: DecisionService, verdicts: VerdictCache | None = None
):
    async def guard_input(state: AssistantState) -> dict[str, Any]:
        question = state.get("question", "")
        principal = state.get("principal")
        with get_tracing().observe("check-safety", as_type="guardrail", input=question) as span:
            # A repeated question reuses a real verdict; a fail-closed "the check did not run" is never cached.
            verdict = await verdicts.get_safety(principal, question) if verdicts else None
            cache_hit = verdict is not None
            if verdict is None:
                verdict = await decision_service.check_safety(question)
                if verdicts is not None:
                    await verdicts.put_safety(principal, question, verdict)
            span.finish(
                {"is_safe": verdict.is_safe},
                decider=verdict.provider_used,
                cache_hit=str(cache_hit).lower(),
            )
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
