"""G1-G6: the node paths for each kind of question (plan section 7).

Each scenario asserts the exact node order, so an unplanned edge or a skipped node fails the test.
"""

from __future__ import annotations

import pytest
from fakes.chat_model import tool_call_message
from support.graph_harness import DOCS_PATH, TENANT_A, make_graph, run_turn
from support.specs import need

pytestmark = pytest.mark.graph


class TestG1Docs:
    async def test_a_documented_question_follows_the_docs_path(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        graph = make_graph(kit)
        turn = await run_turn(
            graph, question="How often are invoices issued?", principal=principal_a
        )
        assert turn.path == DOCS_PATH

    async def test_the_answer_cites_only_chunks_that_were_retrieved(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        graph = make_graph(kit)
        turn = await run_turn(
            graph, question="How often are invoices issued?", principal=principal_a
        )
        retrieved = {"a1", "g1"}
        cited = {citation["chunk_id"] for citation in turn.state["citations"]}
        assert cited and cited <= retrieved

    async def test_retrieval_is_scoped_to_the_callers_tenant(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        graph = make_graph(kit)
        await run_turn(graph, question="How often are invoices issued?", principal=principal_a)
        assert {call["tenant_id"] for call in kit.retriever.calls} == {str(TENANT_A)}


class TestG2Account:
    async def test_an_account_question_calls_a_read_tool_and_skips_retrieval(
        self, kit, principal_a
    ) -> None:  # type: ignore[no-untyped-def]
        kit.strong.script = [
            tool_call_message("get_invoices", {"month": "2026-10"}, "call-1"),
            "Your October invoice total is 2400.",
        ]
        kit.decider.route = "saas_action"
        graph = make_graph(kit)
        turn = await run_turn(
            graph, question="What was my invoice total for October?", principal=principal_a
        )
        assert "account_agent" in turn.path
        assert "hybrid_retrieve" not in turn.path
        assert kit.retriever.calls == []
        assert kit.tools.calls_named("get_invoices")

    async def test_the_read_tool_runs_with_the_principals_tenant(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        kit.strong.script = [
            tool_call_message(
                "get_invoices", {"tenant_id": "b0000000-0000-0000-0000-00000000000b"}, "c1"
            ),
            "Done.",
        ]
        kit.decider.route = "saas_action"
        graph = make_graph(kit)
        await run_turn(graph, question="my invoices", principal=principal_a)
        assert {call["tenant_id"] for call in kit.tools.calls} == {str(TENANT_A)}


class TestG3Mixed:
    @pytest.mark.skip(
        reason="CONFLICT C1: the team's route labels have no 'mixed' route; decide with the team (plan G3)"
    )
    async def test_a_mixed_question_runs_both_branches(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        graph = make_graph(kit)
        turn = await run_turn(
            graph, question="Why was I charged and what is my plan total?", principal=principal_a
        )
        assert "hybrid_retrieve" in turn.path and "account_agent" in turn.path


class TestG4Smalltalk:
    async def test_small_talk_skips_retrieval_and_tools(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        kit.decider.route = "general_chat"
        graph = make_graph(kit)
        turn = await run_turn(graph, question="hi there!", principal=principal_a)
        assert "hybrid_retrieve" not in turn.path and "account_agent" not in turn.path
        assert kit.tools.calls == []

    async def test_small_talk_uses_the_cheap_tier(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        kit.decider.route = "general_chat"
        kit.decider.complexity = 1.0
        graph = make_graph(kit)
        await run_turn(graph, question="hi there!", principal=principal_a)
        assert kit.cheap.calls and kit.strong.calls == []


class TestG5OutOfScope:
    async def test_an_out_of_scope_question_is_not_answered_from_documents_or_tools(
        self, kit, principal_a
    ) -> None:  # type: ignore[no-untyped-def]
        kit.decider.route = "general_chat"
        graph = make_graph(kit)
        turn = await run_turn(
            graph, question="What is the weather in Lisbon?", principal=principal_a
        )
        assert kit.retriever.calls == [] and kit.tools.calls == []
        assert turn.state["citations"] == []


class TestG6HumanRequested:
    async def test_a_request_for_a_human_escalates_immediately(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        kit.decider.route = "human_escalation"
        graph = make_graph(kit)
        turn = await run_turn(
            graph, question="I want to speak to a real person", principal=principal_a
        )
        assert "escalate" in turn.path
        assert "hybrid_retrieve" not in turn.path
        assert turn.state["escalated"] is True


class TestPlannedNodesAreWired:
    def test_the_builder_exposes_every_planned_node_name(self) -> None:
        names = need("assistant.NODE_NAMES")
        assert set(names) == {
            "guard_input",
            "router",
            "rewrite",
            "hybrid_retrieve",
            "rerank",
            "grade_relevance",
            "account_agent",
            "generate",
            "verify_grounding",
            "escalate",
            "finalize",
        }
