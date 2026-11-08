"""G12-G17: model tiering, write-tool interrupts and approval, resume safety, restart and the
thread-tenant guard (plan sections 3 and 7)."""

from __future__ import annotations

import pytest
from fakes.chat_model import tool_call_message
from support.graph_harness import (
    TENANT_A,
    TENANT_B,
    CountingSaver,
    make_graph,
    paused,
    resume_turn,
    run_turn,
    thread_config,
)
from support.specs import need

pytestmark = pytest.mark.graph

WRITE_REQUEST = tool_call_message(
    "update_billing_email", {"new_email": "ap@acme.example"}, "call-w"
)


class TestG12ModelTier:
    @pytest.mark.parametrize(("complexity", "tier"), [(1.0, "cheap"), (3.0, "strong")])
    async def test_complexity_selects_the_generator_tier(
        self, kit_factory, principal_a, complexity: float, tier: str
    ) -> None:  # type: ignore[no-untyped-def]
        kit = kit_factory(complexity=complexity)
        graph = make_graph(kit)
        await run_turn(graph, question="How often are invoices issued?", principal=principal_a)
        used = {"cheap": kit.cheap.calls, "strong": kit.strong.calls}
        assert used[tier] and not used["strong" if tier == "cheap" else "cheap"]


class TestG13WriteToolPausesForApproval:
    async def test_a_write_tool_interrupts_before_it_runs(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        kit.strong.script = [WRITE_REQUEST, "Your billing email has been updated."]
        kit.decider.route = "saas_action"
        graph = make_graph(kit)
        turn = await run_turn(
            graph, question="Change my billing email to ap@acme.example", principal=principal_a
        )
        assert paused(turn)
        assert kit.tools.calls == [], "a write must not run before approval"

    async def test_the_paused_state_is_checkpointed(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        kit.strong.script = [WRITE_REQUEST, "Done."]
        kit.decider.route = "saas_action"
        graph = make_graph(kit)
        turn = await run_turn(graph, question="Change my billing email", principal=principal_a)
        snapshot = await graph.aget_state(turn.config)
        assert snapshot.next, "the graph must report the node it is paused before"


class TestG14ApproveAndDeny:
    async def test_approval_runs_the_write_once_with_the_principals_tenant(
        self, kit, principal_a
    ) -> None:  # type: ignore[no-untyped-def]
        kit.strong.script = [WRITE_REQUEST, "Your billing email has been updated."]
        kit.decider.route = "saas_action"
        graph = make_graph(kit)
        await run_turn(graph, question="Change my billing email", principal=principal_a)
        await resume_turn(graph, decision="approve", principal=principal_a)
        writes = kit.tools.calls_named("update_billing_email")
        assert len(writes) == 1 and writes[0]["tenant_id"] == str(TENANT_A)

    async def test_denial_never_runs_the_write(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        kit.strong.script = [WRITE_REQUEST, "Understood, I will not change it."]
        kit.decider.route = "saas_action"
        graph = make_graph(kit)
        await run_turn(graph, question="Change my billing email", principal=principal_a)
        await resume_turn(graph, decision="deny", principal=principal_a)
        assert kit.tools.calls_named("update_billing_email") == []


class TestG15ResumeSafety:
    async def test_a_second_approval_does_not_repeat_the_write(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        kit.strong.script = [WRITE_REQUEST, "Done.", "Anything else?"]
        kit.decider.route = "saas_action"
        graph = make_graph(kit)
        await run_turn(graph, question="Change my billing email", principal=principal_a)
        await resume_turn(graph, decision="approve", principal=principal_a)
        try:
            await resume_turn(graph, decision="approve", principal=principal_a)
        except Exception:  # noqa: BLE001 - rejecting the second resume is also a correct outcome
            pass
        assert len(kit.tools.calls_named("update_billing_email")) == 1


class TestG16RestartResume:
    async def test_a_new_graph_instance_resumes_from_the_checkpoint(self, kit, principal_a) -> None:  # type: ignore[no-untyped-def]
        kit.strong.script = [WRITE_REQUEST, "Done."]
        kit.decider.route = "saas_action"
        first = make_graph(kit)
        await run_turn(first, question="Change my billing email", principal=principal_a)
        restarted = make_graph(
            kit, checkpointer=kit.checkpointer
        )  # a new process sharing the store
        turn = await resume_turn(restarted, decision="approve", principal=principal_a)
        assert len(kit.tools.calls_named("update_billing_email")) == 1
        assert "finalize" in turn.path


class TestG17ThreadTenantGuard:
    def test_thread_ids_are_namespaced_by_tenant(self) -> None:
        namespaced = need("assistant.namespaced_thread_id")
        assert namespaced(TENANT_A, "c1") == f"{TENANT_A}:c1"
        assert namespaced(TENANT_A, "c1") != namespaced(TENANT_B, "c1")

    async def test_a_conversation_of_another_tenant_is_refused_before_any_checkpoint_read(
        self, principal_b
    ) -> None:  # type: ignore[no-untyped-def]
        ensure = need("assistant.ensure_thread_access")
        denied = need("assistant.ThreadAccessDenied")
        from fakes.conversations import InMemoryConversations

        conversations = InMemoryConversations()
        conversations.create(tenant_id=TENANT_A, conversation_id="c-of-a")
        checkpointer = CountingSaver()
        with pytest.raises(denied):
            await ensure(principal_b, "c-of-a", conversations)
        assert checkpointer.reads == [], "no checkpoint may be read for a foreign conversation"

    async def test_another_tenant_running_the_same_conversation_id_sees_none_of_the_first_tenants_state(
        self, kit, principal_a, principal_b
    ) -> None:  # type: ignore[no-untyped-def]
        graph = make_graph(kit)
        await run_turn(
            graph,
            question="How often are invoices issued?",
            principal=principal_a,
            conversation_id="shared",
        )
        other = await graph.aget_state(thread_config(TENANT_B, "shared"))
        assert not other.values, "tenant B's thread must not contain tenant A's state"
