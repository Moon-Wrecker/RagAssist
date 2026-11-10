"""Each new question starts from clean per-turn state, not from the previous turn's checkpoint."""

from __future__ import annotations

import pytest

from ragassist.modules.assistant.api.router import FRESH_TURN_STATE
from ragassist.modules.assistant.graph.nodes.escalate_node import make_escalate_node
from ragassist.modules.assistant.graph.state import AssistantState

IDENTITY_KEYS = {"question", "principal", "conversation_id"}


def test_only_known_per_turn_fields_are_reset_and_identity_is_never_touched() -> None:
    known = set(AssistantState.__annotations__)
    assert set(FRESH_TURN_STATE) <= known
    assert not set(FRESH_TURN_STATE) & IDENTITY_KEYS


def test_the_answer_status_and_counters_are_cleared() -> None:
    assert FRESH_TURN_STATE["answer"] == ""
    assert FRESH_TURN_STATE["status"] == ""
    assert FRESH_TURN_STATE["escalated"] is False
    assert FRESH_TURN_STATE["citations"] == [] and FRESH_TURN_STATE["tool_calls"] == []
    for counter in ("rewrite_count", "retrieve_count", "generate_count"):
        assert FRESH_TURN_STATE[counter] == 0


@pytest.mark.asyncio
async def test_an_escalation_after_an_earlier_answer_says_it_escalated() -> None:
    node = make_escalate_node()
    stale = {
        "answer": "Hello! I am your assistant."
    }  # what the checkpoint held from the previous turn
    assert (await node(stale))["answer"] == "Hello! I am your assistant."  # type: ignore[arg-type]

    out = await node({**stale, **FRESH_TURN_STATE})  # type: ignore[arg-type]
    assert out["status"] == "escalated"
    assert "escalated your request" in out["answer"]
