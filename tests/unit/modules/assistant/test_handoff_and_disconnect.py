"""Human handoff and disconnect-safe turns.

* While a conversation is ``escalated`` the assistant is silent: the customer message is saved, the graph is not run,
  and the result is the documented handoff on both the JSON and the SSE path. Resolving hands the conversation back.
* When the client disconnects mid-stream (the Stop button) the turn still finishes: the answer is saved, the ticket is
  opened and ``message.created`` is published.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from factories.principals import auth_header, make_token
from langchain_core.messages import AIMessageChunk
from support.asgi_stream import AsgiCall, frame_parts
from support.sse import parse_sse

from ragassist.container import Container
from ragassist.main import create_app
from ragassist.modules.assistant.api import router as assistant_router
from ragassist.modules.assistant.application.conversation_store import get_conversation_store
from ragassist.modules.assistant.application.turns import drain
from ragassist.platform.events import get_event_bus
from ragassist.shared.security.jwt import UserRole


class GraphThatMustNotRun:
    """Any use of the graph fails the test: a handoff must not reach it."""

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        raise AssertionError(f"the graph must not be used during a handoff ({name})")


class GatedGraph:
    """Streams one token, then waits for ``gate`` before finishing: the client can leave in between."""

    def __init__(self, *, status: str = "completed") -> None:
        self.gate = asyncio.Event()
        self.status = status
        self.finished = asyncio.Event()

    async def astream_events(self, input_state, config, version):  # type: ignore[no-untyped-def]
        node = {"langgraph_node": "generate"}
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessageChunk(content="Hello ")},
            "metadata": node,
        }
        await self.gate.wait()
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessageChunk(content="world")},
            "metadata": node,
        }
        yield {
            "event": "on_custom_event",
            "name": "done",
            "data": {"status": self.status},
            "metadata": node,
        }
        self.finished.set()

    async def aget_state(self, config):  # type: ignore[no-untyped-def]
        return SimpleNamespace(tasks=(), values={})

    async def ainvoke(self, input_state, config):  # type: ignore[no-untyped-def]
        await self.gate.wait()
        self.finished.set()
        return {
            "answer": "Hello world",
            "citations": [],
            "route": "rag_search",
            "status": self.status,
        }


def use_graph(monkeypatch: pytest.MonkeyPatch, graph: object) -> None:
    monkeypatch.setattr(Container, "get_assistant_graph", lambda self, checkpointer=None: graph)


@pytest.fixture
def tenant() -> str:
    return str(uuid4())


def who(tenant: str, role: UserRole = UserRole.USER, user: str | None = None) -> dict[str, str]:
    return auth_header(make_token(role=role, tenant_id=tenant, user_id=user or uuid4()))


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://api.test"
    ) as c:
        yield c


async def escalated_conversation(
    client: httpx.AsyncClient, owner: dict[str, str], tenant: str
) -> str:
    cid = (await client.post("/v1/conversations", json={}, headers=owner)).json()["conversation_id"]
    store = get_conversation_store()
    await store.set_status(tenant, cid, "escalated")
    (await store.get(tenant, cid))["ticket_id"] = "TICK-0042"  # type: ignore[index]
    return cid


async def saved(tenant: str, cid: str) -> list[dict]:
    return (await get_conversation_store().get(tenant, cid))["messages"]  # type: ignore[index]


class TestHandoff:
    async def test_json_path_saves_the_message_skips_the_graph_and_returns_the_handoff(
        self, client, tenant, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        use_graph(monkeypatch, GraphThatMustNotRun())
        owner = who(tenant)
        cid = await escalated_conversation(client, owner, tenant)

        response = await client.post(
            f"/v1/conversations/{cid}/messages", json={"content": "Any news?"}, headers=owner
        )

        assert response.status_code == 200
        assert response.json() == {
            "conversation_id": cid,
            "answer": "",
            "citations": [],
            "route": "human_handoff",
            "status": "escalated",
            "interrupt": None,
        }
        messages = await saved(tenant, cid)
        assert [(m["role"], m["text"]) for m in messages] == [("user", "Any news?")]

    async def test_sse_path_sends_the_open_ticket_then_done_and_no_tokens(
        self, client, tenant, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        use_graph(monkeypatch, GraphThatMustNotRun())
        owner = who(tenant)
        cid = await escalated_conversation(client, owner, tenant)

        response = await client.post(
            f"/v1/conversations/{cid}/messages",
            json={"content": "Hello?"},
            headers={**owner, "Accept": "text/event-stream"},
        )

        stream = parse_sse(response.text)
        assert stream.names() == ["escalated", "done"]
        assert stream.of("escalated")[0].json() == {
            "ticket_id": "TICK-0042",
            "status": "open",
            "priority": "high",
        }
        assert json.loads(stream.of("done")[0].data) == {
            "conversation_id": cid,
            "status": "escalated",
        }
        assert [m["role"] for m in await saved(tenant, cid)] == ["user"]

    async def test_the_handoff_announces_the_message_to_the_owner_and_the_inbox(
        self, client, tenant, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        use_graph(monkeypatch, GraphThatMustNotRun())
        owner = who(tenant)
        cid = await escalated_conversation(client, owner, tenant)
        await client.post(
            f"/v1/conversations/{cid}/messages", json={"content": "Hi"}, headers=owner
        )

        published = [(e.type, dict(e.data)) for e in get_event_bus().published]  # type: ignore[attr-defined]
        assert ("message.created", {"conversation_id": cid}) in published
        assert ("escalation.changed", {"conversation_id": cid}) in published

    async def test_resolving_hands_the_conversation_back_to_the_assistant(
        self, client, tenant, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        graph = GatedGraph()
        graph.gate.set()
        use_graph(monkeypatch, graph)
        owner = who(tenant)
        cid = await escalated_conversation(client, owner, tenant)

        resolved = await client.post(
            f"/v1/escalations/{cid}/resolve", headers=who(tenant, UserRole.AGENT)
        )
        assert resolved.status_code == 200

        answer = await client.post(
            f"/v1/conversations/{cid}/messages", json={"content": "Thanks, one more"}, headers=owner
        )
        assert answer.status_code == 200
        body = answer.json()
        assert (
            body["answer"] == "Hello world"
            and body["route"] == "rag_search"
            and body["status"] == "completed"
        )
        assert [m["role"] for m in await saved(tenant, cid)] == ["user", "assistant"]

    async def test_resolving_and_replying_publish_conversation_events(
        self, client, tenant, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        use_graph(monkeypatch, GraphThatMustNotRun())
        owner_id = str(uuid4())
        owner = who(tenant, user=owner_id)
        cid = await escalated_conversation(client, owner, tenant)
        agent = who(tenant, UserRole.AGENT)

        assert (
            await client.post(f"/v1/escalations/{cid}/reply", json={"text": "On it"}, headers=agent)
        ).status_code == 200
        assert (
            await client.post(f"/v1/escalations/{cid}/resolve", headers=agent)
        ).status_code == 200

        published = get_event_bus().published  # type: ignore[attr-defined]
        types = [e.type for e in published]
        assert (
            "message.created" in types
            and "conversation.updated" in types
            and "escalation.changed" in types
        )
        updated = next(e for e in published if e.type == "conversation.updated")
        assert updated.owner_id == owner_id and dict(updated.data) == {"conversation_id": cid}
        assert "On it" not in json.dumps([e.to_json() for e in published]), (
            "no content travels in events"
        )


class TestDisconnectSafePersistence:
    async def start_stream(self, app, headers, cid) -> AsgiCall:  # type: ignore[no-untyped-def]
        call = AsgiCall(
            app,
            f"/v1/conversations/{cid}/messages",
            method="POST",
            headers={**headers, "accept": "text/event-stream", "content-type": "application/json"},
            body=json.dumps({"content": "please help"}).encode(),
        )
        return await call.start()

    async def test_the_answer_is_saved_after_the_client_disconnects(
        self, tenant, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        graph = GatedGraph()
        use_graph(monkeypatch, graph)
        app = create_app()
        owner = who(tenant)
        cid = str(uuid4())

        call = await self.start_stream(app, owner, cid)
        first = (await call.frames(1))[0]
        assert frame_parts(first) == ("token", {"text": "Hello "})

        await call.disconnect()  # Stop: the client is gone before the turn has finished
        assert [m["role"] for m in await saved(tenant, cid)] == ["user"], "nothing is saved yet"

        graph.gate.set()
        await asyncio.wait_for(graph.finished.wait(), 3)
        await drain(timeout=3)

        messages = await saved(tenant, cid)
        assert [(m["role"], m["text"]) for m in messages] == [
            ("user", "please help"),
            ("assistant", "Hello world"),
        ]
        assert ("message.created", {"conversation_id": cid}) in [
            (e.type, dict(e.data))
            for e in get_event_bus().published  # type: ignore[attr-defined]
        ]

    async def test_the_ticket_is_opened_even_if_the_client_left(self, tenant, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        graph = GatedGraph(status="escalated")
        use_graph(monkeypatch, graph)
        tickets: list[tuple[str, str]] = []

        async def fake_open_ticket(store, principal, conversation_id, question, events=None):  # type: ignore[no-untyped-def]
            tickets.append((conversation_id, question))
            return {"ticket_id": "TICK-7", "status": "open", "priority": "high"}

        monkeypatch.setattr(assistant_router, "_open_ticket", fake_open_ticket)
        app = create_app()
        cid = str(uuid4())

        call = await self.start_stream(app, who(tenant), cid)
        await call.frames(1)
        await call.disconnect()
        graph.gate.set()
        await asyncio.wait_for(graph.finished.wait(), 3)
        await drain(timeout=3)

        assert tickets == [(cid, "please help")]
        assert [m["role"] for m in await saved(tenant, cid)] == ["user", "assistant"]

    async def test_a_connected_client_still_receives_the_whole_stream(
        self, tenant, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        graph = GatedGraph()
        graph.gate.set()
        use_graph(monkeypatch, graph)
        call = await self.start_stream(create_app(), who(tenant), str(uuid4()))
        names = []
        while True:
            chunk = await call.chunk(timeout=3)
            if chunk is None:
                break
            names.extend(frame_parts(f)[0] for f in chunk.split("\n\n") if f)
        assert names[0] == "token" and names[-1] == "done"
        await drain(timeout=3)

    async def test_the_json_path_survives_a_cancelled_request(
        self, client, tenant, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        graph = GatedGraph()
        use_graph(monkeypatch, graph)
        owner = who(tenant)
        cid = (await client.post("/v1/conversations", json={}, headers=owner)).json()[
            "conversation_id"
        ]

        request = asyncio.create_task(
            client.post(
                f"/v1/conversations/{cid}/messages", json={"content": "slow one"}, headers=owner
            )
        )
        await asyncio.sleep(0.1)
        request.cancel()  # the caller gives up
        with pytest.raises(asyncio.CancelledError):
            await request
        graph.gate.set()
        await asyncio.wait_for(graph.finished.wait(), 3)
        await drain(timeout=3)

        assert [m["role"] for m in await saved(tenant, cid)] == ["user", "assistant"]
