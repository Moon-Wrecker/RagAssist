"""Query rewrite node expanding query for improved recall."""

from __future__ import annotations

from typing import Any
from ragassist.modules.assistant.graph.state import AssistantState


def make_rewrite_node():  # type: ignore[no-untyped-def]
    async def rewrite(state: AssistantState) -> dict[str, Any]:
        count = state.get("rewrite_count", 0) + 1
        original = state.get("question", "")
        current = state.get("current_query") or original

        if count > 1:
            query = f"{current} details"
        else:
            query = current

        return {
            "rewrite_count": count,
            "current_query": query,
        }

    return rewrite
