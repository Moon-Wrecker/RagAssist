"""Live events must never cross a tenant or an owner boundary, and never carry content.

Streams are opened through the real application; events come from the real publishers (agent reply, escalation,
resolve, document upload) as well as from the bus directly.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from factories.principals import auth_header, make_token
from support.asgi_stream import AsgiCall, frame_parts

from ragassist.main import create_app
from ragassist.modules.assistant.application.conversation_store import get_conversation_store
from ragassist.platform.events import (
    conversation_updated,
    document_changed,
    escalation_changed,
    get_event_bus,
    job_updated,
    message_created,
)
from ragassist.shared.security.jwt import UserRole

pytestmark = pytest.mark.security

TENANT_A = uuid4()
TENANT_B = uuid4()


class World:
    """Streams for every kind of viewer, opened once."""

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app
        self.users: dict[str, tuple[AsgiCall, str]] = {}

    async def open(self, name: str, tenant: object, role: UserRole) -> str:
        user_id = str(uuid4())
        token = make_token(role=role, tenant_id=tenant, user_id=user_id)  # type: ignore[arg-type]
        call = await AsgiCall(self.app, "/v1/events", headers=auth_header(token)).start()
        assert call.status == 200
        await call.frames(1)  # ready
        self.users[name] = (call, user_id)
        return user_id

    async def received(self, name: str, quiet: float = 0.25) -> list[tuple[str, dict]]:
        """Everything that arrives on the stream until it has been quiet for ``quiet`` seconds."""
        call, _ = self.users[name]
        out: list[tuple[str, dict]] = []
        while True:
            try:
                chunk = await call.chunk(timeout=quiet)
            except TimeoutError:
                return out
            if chunk is None:
                return out
            out.extend(frame_parts(f) for f in chunk.split("\n\n") if f and not f.startswith(":"))

    async def close(self) -> None:
        for call, _ in self.users.values():
            await call.close()


@pytest.fixture
async def world():  # type: ignore[no-untyped-def]
    w = World(create_app())
    yield w
    await w.close()


async def open_everyone(w: World) -> dict[str, str]:
    ids = {}
    for name, tenant, role in [
        ("a_user", TENANT_A, UserRole.USER),
        ("a_user2", TENANT_A, UserRole.USER),
        ("a_agent", TENANT_A, UserRole.AGENT),
        ("a_admin", TENANT_A, UserRole.ADMIN),
        ("b_user", TENANT_B, UserRole.USER),
        ("b_agent", TENANT_B, UserRole.AGENT),
        ("b_admin", TENANT_B, UserRole.ADMIN),
    ]:
        ids[name] = await w.open(name, tenant, role)
    return ids


class TestNoCrossTenantEvents:
    async def test_no_event_of_tenant_a_reaches_tenant_b_in_any_role(self, world) -> None:  # type: ignore[no-untyped-def]
        ids = await open_everyone(world)
        bus = get_event_bus()
        await bus.publish(job_updated(TENANT_A, "j1", "d1"))
        await bus.publish(document_changed(TENANT_A, "d1"))
        await bus.publish(escalation_changed(TENANT_A, "c1", "T-1"))
        await bus.publish(message_created(TENANT_A, "c1", ids["a_user"]))
        await bus.publish(conversation_updated(TENANT_A, "c1", ids["a_user"]))
        for name in ("b_user", "b_agent", "b_admin"):
            assert await world.received(name) == [], f"{name} received a foreign event"

    async def test_the_same_holds_the_other_way_round(self, world) -> None:  # type: ignore[no-untyped-def]
        ids = await open_everyone(world)
        await get_event_bus().publish(message_created(TENANT_B, "cb", ids["b_user"]))
        for name in ("a_user", "a_user2", "a_agent", "a_admin"):
            assert await world.received(name) == []


class TestNoCrossUserEvents:
    async def test_a_conversation_event_reaches_its_owner_and_staff_but_not_other_users(
        self, world
    ) -> None:  # type: ignore[no-untyped-def]
        ids = await open_everyone(world)
        await get_event_bus().publish(message_created(TENANT_A, "conv-9", ids["a_user"]))
        assert await world.received("a_user2") == []
        assert [e for e, _ in await world.received("a_user")] == ["message.created"]
        assert [e for e, _ in await world.received("a_agent")] == ["message.created"]
        assert [e for e, _ in await world.received("a_admin")] == ["message.created"]

    async def test_a_user_never_receives_staff_or_admin_events(self, world) -> None:  # type: ignore[no-untyped-def]
        await open_everyone(world)
        bus = get_event_bus()
        await bus.publish(escalation_changed(TENANT_A, "c1"))
        await bus.publish(job_updated(TENANT_A, "j", "d"))
        await bus.publish(document_changed(TENANT_A, "d"))
        assert await world.received("a_user") == []
        assert await world.received("a_user2") == []
        assert [e for e, _ in await world.received("a_agent")] == [
            "escalation.changed"
        ]  # agents: no document events
        assert sorted(e for e, _ in await world.received("a_admin")) == [
            "document.changed",
            "escalation.changed",
            "job.updated",
        ]

    async def test_identity_comes_from_the_token_not_the_request(self, world) -> None:  # type: ignore[no-untyped-def]
        """A query string naming another tenant or user changes nothing."""
        token = make_token(role=UserRole.USER, tenant_id=TENANT_A)
        call = AsgiCall(world.app, "/v1/events", headers=auth_header(token))
        call._scope["query_string"] = f"tenant_id={TENANT_B}&user_id={uuid4()}&role=admin".encode()
        await call.start()
        await call.frames(1)
        await get_event_bus().publish(document_changed(TENANT_B, "foreign"))
        await get_event_bus().publish(document_changed(TENANT_A, "admins-only"))
        with pytest.raises(asyncio.TimeoutError):
            await call.chunk(timeout=0.3)
        await call.close()


class TestEventsFromRealPublishers:
    async def test_an_agent_reply_notifies_the_owner_only_and_carries_no_text(self, world) -> None:  # type: ignore[no-untyped-def]
        ids = await open_everyone(world)
        store = get_conversation_store()
        cid = str(uuid4())
        store.create(
            tenant_id=TENANT_A, conversation_id=cid, user_id=ids["a_user"], status="escalated"
        )  # type: ignore[attr-defined]
        secret_text = f"private reply {uuid4()}"
        agent = auth_header(make_token(role=UserRole.AGENT, tenant_id=TENANT_A))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=world.app), base_url="http://api.test"
        ) as c:
            response = await c.post(
                f"/v1/escalations/{cid}/reply", json={"text": secret_text}, headers=agent
            )
        assert response.status_code == 200

        owner = await world.received("a_user")
        assert [e for e, _ in owner] == ["message.created"] and owner[0][1] == {
            "conversation_id": cid
        }
        assert await world.received("a_user2") == []
        for name in ("b_user", "b_agent", "b_admin"):
            assert await world.received(name) == []
        wire = json.dumps([e.to_json() for e in get_event_bus().published])  # type: ignore[attr-defined]
        assert secret_text not in wire, "message text must never travel through the event channel"

    async def test_a_document_upload_notifies_admins_of_that_tenant_only(self, world) -> None:  # type: ignore[no-untyped-def]
        await open_everyone(world)
        admin = auth_header(make_token(role=UserRole.ADMIN, tenant_id=TENANT_A))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=world.app), base_url="http://api.test"
        ) as c:
            response = await c.post(
                "/v1/documents",
                files={"file": ("guide.md", b"# Guide\n\nHello", "text/markdown")},
                headers=admin,
            )
        assert response.status_code == 202
        types = sorted(e for e, _ in await world.received("a_admin"))
        assert types == ["document.changed", "job.updated"]
        for name in ("a_user", "a_agent", "b_admin", "b_user"):
            assert await world.received(name) == []
