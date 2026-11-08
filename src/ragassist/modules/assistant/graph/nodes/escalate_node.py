"""Escalate node routing unresolved questions to human support."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState


def make_escalate_node():  # type: ignore[no-untyped-def]
    async def escalate(state: AssistantState) -> dict[str, Any]:
        ans = state.get("answer")
        if not ans:
            ans = "I have escalated your request to a support agent who will follow up shortly."

        return {
            "escalated": True,
            "status": "escalated",
            "answer": ans,
        }

    return escalate
