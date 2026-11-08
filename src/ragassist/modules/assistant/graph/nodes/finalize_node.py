"""Finalize node ensuring all output contracts and events are emitted."""

from __future__ import annotations

from typing import Any
from langchain_core.callbacks.manager import adispatch_custom_event
from ragassist.modules.assistant.graph.state import AssistantState


def make_finalize_node():  # type: ignore[no-untyped-def]
    async def finalize(state: AssistantState) -> dict[str, Any]:
        status = state.get("status") or ("escalated" if state.get("escalated") else "completed")
        citations = state.get("citations", [])

        # Emit custom events in strict order: citation before done
        await adispatch_custom_event("citation", {"citations": citations})
        await adispatch_custom_event("done", {"status": status})

        return {
            "status": status,
            "escalated": state.get("escalated", False),
            "citations": citations,
            "tool_calls": state.get("tool_calls", []),
            "model_used": state.get("model_used", ""),
            "decider_used": state.get("decider_used", ""),
            "complexity": state.get("complexity", 2.0),
            "route": state.get("route", "rag_search"),
            "answer": state.get("answer", ""),
        }

    return finalize
