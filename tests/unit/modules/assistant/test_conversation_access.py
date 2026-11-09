"""Per-user access inside a tenant, escalation listing and the approval endpoint.

Tenant isolation is the database's job; inside one tenant a conversation still belongs to the user who opened
it. Plain users see only their own, staff see the tenant's, and a paused write action can be decided only by
the conversation's owner or an admin, for the interrupt the checkpoint is really paused on.
"""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from fakes.chat_model import tool_call_message
from support.graph_harness import make_graph, make_kit
from support.sse import parse_sse

from ragassist.container import Container
from ragassist.main import create_app
from ragassist.modules.assistant.api.router import get_conversation_store
from ragassist.shared.security.jwt import UserRole, create_access_token

WRITE_REQUEST = tool_call_message("update_billing_email", {"new_email": "ap@acme.example"}, "call-w")


def headers(tenant: str, role: UserRole = UserRole.USER, user: str | None = None) -> dict[str, str]:
    token = create_access_token(user_id=user or str(uuid4()), tenant_id=tenant, role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant() -> str:
    return str(uuid4())  # a fresh tenant per test: the in-memory store is process-wide


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as c:
        yield c


async def open_conversation(client: httpx.AsyncClient, who: dict[str, str], title: str = "T") -> str:
    created = await client.post("/v1/conversations", json={"title": title}, headers=who)
    assert created.status_code == 201
    return created.json()["conversation_id"]


class TestOwnership:
    async def test_another_user_of_the_tenant_cannot_read_a_conversation(self, client, tenant) -> None:  # type: ignore[no-untyped-def]
        owner, other = headers(tenant), headers(tenant)
        cid = await open_conversation(client, owner)
        assert (await client.get(f"/v1/conversations/{cid}", headers=owner)).status_code == 200
        assert (await client.get(f"/v1/conversations/{cid}", headers=other)).status_code == 404

    async def test_another_user_cannot_post_to_it(self, client, tenant) -> None:  # type: ignore[no-untyped-def]
        owner, other = headers(tenant), headers(tenant)
        cid = await open_conversation(client, owner)
        denied = await client.post(
            f"/v1/conversations/{cid}/messages", json={"content": "hi"}, headers=other
        )
        assert denied.status_code == 404
        sse = await client.post(
            f"/v1/conversations/{cid}/messages",
            json={"content": "hi"},
            headers={**other, "Accept": "text/event-stream"},
        )
        assert sse.status_code == 404

    async def test_staff_can_read_any_conversation_of_the_tenant(self, client, tenant) -> None:  # type: ignore[no-untyped-def]
        cid = await open_conversation(client, headers(tenant))
        for role in (UserRole.AGENT, UserRole.ADMIN):
            assert (
                await client.get(f"/v1/conversations/{cid}", headers=headers(tenant, role))
            ).status_code == 200

    async def test_a_conversation_without_a_recorded_owner_is_staff_only(self, client, tenant) -> None:  # type: ignore[no-untyped-def]
        cid = str(uuid4())
        get_conversation_store().create(tenant_id=tenant, conversation_id=cid)
        assert (await client.get(f"/v1/conversations/{cid}", headers=headers(tenant))).status_code == 404
        assert (
            await client.get(f"/v1/conversations/{cid}", headers=headers(tenant, UserRole.AGENT))
        ).status_code == 200

    async def test_the_list_holds_only_the_callers_conversations_unless_staff(self, client, tenant) -> None:  # type: ignore[no-untyped-def]
        alice, bob = headers(tenant), headers(tenant)
        mine = await open_conversation(client, alice)
        await open_conversation(client, bob)
        listed = (await client.get("/v1/conversations", headers=alice)).json()
        assert [c["conversation_id"] for c in listed["items"]] == [mine]
        assert listed["total"] == 1
        staff = (await client.get("/v1/conversations", headers=headers(tenant, UserRole.AGENT))).json()
        assert staff["total"] == 2


class TestEscalationList:
    async def test_a_plain_user_cannot_list_escalations(self, client, tenant) -> None:  # type: ignore[no-untyped-def]
        denied = await client.get("/v1/escalations", headers=headers(tenant))
        assert denied.status_code == 403

    async def test_the_status_filter_applies_before_paging(self, client, tenant) -> None:  # type: ignore[no-untyped-def]
        store = get_conversation_store()
        for _ in range(3):
            store.create(tenant_id=tenant, conversation_id=str(uuid4()), status="open")
        escalated = {str(uuid4()) for _ in range(2)}
        for cid in escalated:
            store.create(tenant_id=tenant, conversation_id=cid, status="escalated")
        agent = headers(tenant, UserRole.AGENT)

        first = (await client.get("/v1/escalations?limit=1&offset=0", headers=agent)).json()
        second = (await client.get("/v1/escalations?limit=1&offset=1", headers=agent)).json()
        assert first["total"] == second["total"] == 2
        assert {first["items"][0]["escalation_id"], second["items"][0]["escalation_id"]} == escalated


@pytest.fixture
def write_graph(monkeypatch):  # type: ignore[no-untyped-def]
    """The real assistant graph, scripted so the first turn asks for a write and pauses for approval."""
    kit = make_kit(route="saas_action")
    kit.strong.script = [WRITE_REQUEST, "Your billing email has been updated."]
    graph = make_graph(kit)
    monkeypatch.setattr(Container, "get_assistant_graph", lambda self, checkpointer=None: graph)
    return kit


async def ask_for_the_write(client: httpx.AsyncClient, who: dict[str, str]) -> tuple[str, dict]:
    cid = await open_conversation(client, who)
    response = await client.post(
        f"/v1/conversations/{cid}/messages",
        json={"content": "Change my billing email to ap@acme.example"},
        headers={**who, "Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    stream = parse_sse(response.text)
    assert stream.names()[-1] == "done"
    assert json.loads(stream.of("done")[0].data)["status"] == "interrupted"
    return cid, stream.of("interrupt")[0].json()


class TestApprovalIsBoundToThePendingAction:
    async def test_the_interrupt_frame_carries_the_id_and_the_proposed_call(
        self, client, tenant, write_graph
    ) -> None:  # type: ignore[no-untyped-def]
        _, interrupt = await ask_for_the_write(client, headers(tenant, UserRole.ADMIN))
        assert interrupt["interrupt_id"]
        assert interrupt["tool"] == "update_billing_email"
        assert interrupt["arguments"] == {"new_email": "ap@acme.example"}
        assert write_graph.tools.calls == [], "nothing runs before a decision"

    async def test_an_unknown_interrupt_id_is_refused_and_nothing_runs(
        self, client, tenant, write_graph
    ) -> None:  # type: ignore[no-untyped-def]
        owner = headers(tenant, UserRole.ADMIN)
        cid, _ = await ask_for_the_write(client, owner)
        refused = await client.post(
            f"/v1/conversations/{cid}/actions/not-the-pending-id", json={"approved": True}, headers=owner
        )
        assert refused.status_code == 409
        assert write_graph.tools.calls == []

    async def test_a_conversation_with_nothing_pending_refuses_any_decision(self, client, tenant) -> None:  # type: ignore[no-untyped-def]
        owner = headers(tenant)
        cid = await open_conversation(client, owner)
        refused = await client.post(
            f"/v1/conversations/{cid}/actions/anything", json={"approved": True}, headers=owner
        )
        assert refused.status_code == 409

    async def test_only_the_owner_or_an_admin_may_decide(self, client, tenant, write_graph) -> None:  # type: ignore[no-untyped-def]
        owner_id = str(uuid4())
        owner = headers(tenant, UserRole.USER, owner_id)
        cid, interrupt = await ask_for_the_write(client, owner)
        path = f"/v1/conversations/{cid}/actions/{interrupt['interrupt_id']}"

        assert (await client.post(path, json={"approved": True}, headers=headers(tenant))).status_code == 404
        assert (
            await client.post(path, json={"approved": True}, headers=headers(tenant, UserRole.AGENT))
        ).status_code == 403
        assert write_graph.tools.calls == []

    async def test_approval_runs_exactly_the_approved_call_and_saves_the_outcome(
        self, client, tenant, write_graph
    ) -> None:  # type: ignore[no-untyped-def]
        admin = headers(tenant, UserRole.ADMIN)
        cid, interrupt = await ask_for_the_write(client, admin)
        path = f"/v1/conversations/{cid}/actions/{interrupt['interrupt_id']}"

        decided = await client.post(path, json={"approved": True, "reason": "verified"}, headers=admin)
        assert decided.status_code == 200
        body = decided.json()
        assert body["status"] == "resumed" and body["answer"]
        writes = write_graph.tools.calls_named("update_billing_email")
        assert len(writes) == 1 and writes[0]["arguments"] == {"new_email": "ap@acme.example"}

        history = (await client.get(f"/v1/conversations/{cid}", headers=admin)).json()["messages"]
        assert history[-1]["role"] == "assistant" and history[-1]["text"] == body["answer"]

        again = await client.post(path, json={"approved": True}, headers=admin)
        assert again.status_code == 409, "a decision can be made once"
        assert len(write_graph.tools.calls_named("update_billing_email")) == 1

    async def test_denial_never_runs_the_write(self, client, tenant, write_graph) -> None:  # type: ignore[no-untyped-def]
        admin = headers(tenant, UserRole.ADMIN)
        cid, interrupt = await ask_for_the_write(client, admin)
        denied = await client.post(
            f"/v1/conversations/{cid}/actions/{interrupt['interrupt_id']}",
            json={"approved": False},
            headers=admin,
        )
        assert denied.status_code == 200
        assert write_graph.tools.calls_named("update_billing_email") == []

    async def test_a_failed_resume_is_reported_not_called_resumed(
        self, client, tenant, write_graph
    ) -> None:  # type: ignore[no-untyped-def]
        admin = headers(tenant, UserRole.ADMIN)
        cid, interrupt = await ask_for_the_write(client, admin)

        async def boom(*_a, **_k):  # type: ignore[no-untyped-def]
            raise RuntimeError("upstream host 10.0.0.7 refused the connection")

        write_graph.tools.invoke = boom  # type: ignore[method-assign]
        failed = await client.post(
            f"/v1/conversations/{cid}/actions/{interrupt['interrupt_id']}",
            json={"approved": True},
            headers=admin,
        )
        assert failed.status_code == 502
        assert "10.0.0.7" not in failed.text
