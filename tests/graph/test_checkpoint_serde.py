"""A paused approval must resume without LangGraph complaining about our own types.

LangGraph warns (and will soon refuse) when a checkpoint contains a type outside its allow-list. This runs a
full pause and resume with the production serializer and fails on any such warning.
"""

from __future__ import annotations

import logging

import pytest
from fakes.chat_model import tool_call_message
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from support.graph_harness import make_graph, make_kit, paused, run_turn, thread_config

from ragassist.modules.assistant.graph.serde import ALLOWED_MSGPACK_MODULES, checkpoint_serde

pytestmark = pytest.mark.graph


async def test_a_paused_turn_resumes_with_no_unregistered_type_warning(
    principal_a, caplog: pytest.LogCaptureFixture
) -> None:  # type: ignore[no-untyped-def]
    kit = make_kit(route="saas_action")
    kit.checkpointer = MemorySaver(serde=checkpoint_serde())
    kit.strong.script = [
        tool_call_message("update_billing_email", {"new_email": "ap@acme.example"}, "call-w"),
        "Done.",
    ]
    graph = make_graph(kit)

    with caplog.at_level(logging.WARNING, logger="langgraph.checkpoint.serde.jsonplus"):
        turn = await run_turn(graph, question="Change my billing email", principal=principal_a)
        assert paused(turn)
        async for _ in graph.astream(
            Command(resume={"decision": "approve"}),
            thread_config(principal_a.tenant_id, "c1"),
            stream_mode="updates",
        ):
            pass

    unregistered = [r.getMessage() for r in caplog.records if "unregistered type" in r.getMessage()]
    assert unregistered == []
    assert len(kit.tools.calls_named("update_billing_email")) == 1


async def test_a_retrieval_turn_checkpoints_hits_without_warning(
    principal_a, caplog: pytest.LogCaptureFixture
) -> None:  # type: ignore[no-untyped-def]
    kit = make_kit()
    kit.checkpointer = MemorySaver(serde=checkpoint_serde())
    graph = make_graph(kit)

    with caplog.at_level(logging.WARNING, logger="langgraph.checkpoint.serde.jsonplus"):
        await run_turn(graph, question="How often are invoices issued?", principal=principal_a)
        await graph.aget_state(thread_config(principal_a.tenant_id, "c1"))

    assert [r.getMessage() for r in caplog.records if "unregistered type" in r.getMessage()] == []


def test_the_allow_list_names_only_types_in_this_project() -> None:
    assert all(module.startswith("ragassist.") for module, _ in ALLOWED_MSGPACK_MODULES)
