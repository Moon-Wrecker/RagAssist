"""The account agent must not carry a pending tool call from one turn into the next.

A write needs approval, so the turn pauses. If the user never answers and asks something else on the same
conversation, the new turn must start clean. The node keeps the pending call in a module-level dict keyed by
thread, so the stale write is replayed instead (DEFECT-41). The same leak makes the graph suite order-dependent
(it failed once in CI under random ordering).
"""

from __future__ import annotations

import pytest
from factories.principals import make_principal
from fakes.chat_model import tool_call_message
from support.defects import defect
from support.graph_harness import TENANT_A, make_graph, make_kit, paused, run_turn

pytestmark = pytest.mark.graph


@defect("DEFECT-41")
async def test_an_abandoned_approval_is_not_replayed_on_the_next_turn() -> None:
    kit = make_kit(route="saas_action")
    principal = make_principal(tenant_id=TENANT_A)
    graph = make_graph(kit)

    # Turn 1: the model asks to change the billing email; the turn pauses for approval and is abandoned.
    kit.strong.script = [
        tool_call_message("update_billing_email", {"new_email": "x@y.example"}, "w1")
    ]
    first = await run_turn(
        graph, question="change my billing email", principal=principal, conversation_id="same"
    )
    assert paused(first), "a write must pause for approval"

    # Turn 2 on the same conversation: an unrelated read. It must run as a fresh turn.
    kit.strong.script = [
        tool_call_message("get_account_overview", {}, "r1"),
        "Your plan is active.",
    ]
    second = await run_turn(
        graph, question="what is my plan?", principal=principal, conversation_id="same"
    )

    assert not paused(second), "the stale write was replayed and paused the new turn"
    assert len(kit.tools.calls_named("get_account_overview")) == 1
    assert kit.tools.calls_named("update_billing_email") == []
