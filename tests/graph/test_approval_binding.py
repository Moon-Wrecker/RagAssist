"""A human approves one specific call; that call, and nothing else, must run.

The account agent re-executes from the top when a paused turn resumes. If the model is asked again (a
restart, another worker, an evicted cache entry) it may propose different arguments. The router therefore
passes back the tool, arguments and call id stored with the checkpointed interrupt, and the node runs those.
"""

from __future__ import annotations

import pytest
from fakes.chat_model import tool_call_message
from langgraph.types import Command
from support.graph_harness import make_graph, paused, run_turn, thread_config

from ragassist.modules.assistant.graph.nodes import account_agent_node

pytestmark = pytest.mark.graph

PROPOSED = tool_call_message("update_billing_email", {"new_email": "ap@acme.example"}, "call-w")
SWAPPED = tool_call_message(
    "update_billing_email", {"new_email": "attacker@evil.example"}, "call-x"
)


async def resume(graph, principal, payload: dict) -> None:  # type: ignore[no-untyped-def]
    config = thread_config(principal.tenant_id, "c1")
    async for _ in graph.astream(Command(resume=payload), config, stream_mode="updates"):
        pass


class TestTheApprovedCallIsWhatRuns:
    async def test_a_regenerated_proposal_cannot_change_the_arguments(
        self, kit, principal_a
    ) -> None:  # type: ignore[no-untyped-def]
        kit.strong.script = [PROPOSED]
        kit.decider.route = "saas_action"
        graph = make_graph(kit)
        turn = await run_turn(graph, question="Change my billing email", principal=principal_a)
        assert paused(turn)

        # The process "restarts": the proposal cache is gone and the model now answers differently.
        account_agent_node._PENDING_TOOL_CALLS.clear()
        kit.strong.script = [SWAPPED, "Done."]
        await resume(
            graph,
            principal_a,
            {
                "decision": "approve",
                "tool": "update_billing_email",
                "arguments": {"new_email": "ap@acme.example"},
                "call_id": "call-w",
            },
        )

        writes = kit.tools.calls_named("update_billing_email")
        assert [w["arguments"] for w in writes] == [{"new_email": "ap@acme.example"}]


class TestFailClosed:
    async def test_an_unreadable_write_policy_still_asks_for_approval(
        self, kit, principal_a
    ) -> None:  # type: ignore[no-untyped-def]
        def broken(_name: str) -> bool:
            raise RuntimeError("policy backend down")

        kit.tools.is_write = broken  # type: ignore[method-assign]
        kit.strong.script = [tool_call_message("get_invoices", {}, "r1"), "Here you go."]
        kit.decider.route = "saas_action"
        turn = await run_turn(make_graph(kit), question="Show my invoices", principal=principal_a)
        assert paused(turn), "when the policy cannot be read, a human decides"
        assert kit.tools.calls == []

    async def test_a_caller_who_may_not_write_is_refused_before_any_prompt(
        self, kit, principal_a
    ) -> None:  # type: ignore[no-untyped-def]
        def authorize(_name: str, _principal: object) -> None:
            raise PermissionError("Admin role required")

        kit.tools.authorize = authorize  # type: ignore[attr-defined]
        kit.strong.script = [PROPOSED, "Only an admin can change the billing email."]
        kit.decider.route = "saas_action"
        turn = await run_turn(
            make_graph(kit), question="Change my billing email", principal=principal_a
        )
        assert not paused(turn), "nobody is asked to approve an action the caller cannot run"
        assert kit.tools.calls == []
        assert turn.state["answer"] == "Only an admin can change the billing email."


class TestTheProposalCacheIsBounded:
    def test_old_entries_are_evicted(self) -> None:
        account_agent_node._PENDING_TOOL_CALLS.clear()
        for n in range(account_agent_node.MAX_PENDING_TOOL_CALLS + 25):
            account_agent_node._remember(f"t:{n}", "q", object())
        assert (
            len(account_agent_node._PENDING_TOOL_CALLS) == account_agent_node.MAX_PENDING_TOOL_CALLS
        )
        assert "t:0" not in account_agent_node._PENDING_TOOL_CALLS
        account_agent_node._PENDING_TOOL_CALLS.clear()
