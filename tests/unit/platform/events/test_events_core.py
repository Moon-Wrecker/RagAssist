"""Events platform: the event model (ids only), the audience filter, the bounded fan-out and the stream framing."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from support.asgi_stream import frame_parts

from ragassist.platform.events import (
    Audience,
    Event,
    InMemoryEventBus,
    InvalidEvent,
    TooManyStreams,
    Viewer,
    conversation_updated,
    document_changed,
    escalation_changed,
    job_updated,
    message_created,
    publish_safely,
    visible_to,
)
from ragassist.platform.events.adapters.postgres import PostgresEventBus
from ragassist.platform.events.hub import RESYNC_MARKER, EventHub, Subscription
from ragassist.platform.events.router import event_frames

TENANT = str(uuid4())
OTHER_TENANT = str(uuid4())


def viewer(role: str = "user", tenant: str = TENANT, user: str | None = None) -> Viewer:
    return Viewer(tenant_id=tenant, user_id=user or str(uuid4()), role=role)


class TestEventModel:
    def test_builders_carry_only_ids(self) -> None:
        events = [
            job_updated(TENANT, "j1", "d1"),
            document_changed(TENANT, "d1"),
            message_created(TENANT, "c1", "u1"),
            conversation_updated(TENANT, "c1", "u1"),
            escalation_changed(TENANT, "c1", "TICK-1"),
        ]
        assert {k for e in events for k in e.payload()} <= {"job_id", "document_id", "conversation_id", "ticket_id"}

    @pytest.mark.parametrize("key", ["text", "content", "answer", "summary", "email"])
    def test_a_payload_key_that_is_not_an_id_is_refused(self, key: str) -> None:
        with pytest.raises(InvalidEvent):
            Event("message.created", TENANT, Audience.STAFF, {key: "hello"})

    def test_an_unknown_type_or_oversized_id_is_refused(self) -> None:
        with pytest.raises(InvalidEvent):
            Event("password.changed", TENANT, Audience.STAFF)
        with pytest.raises(InvalidEvent):
            Event("message.created", TENANT, Audience.STAFF, {"conversation_id": "x" * 500})

    def test_the_json_round_trip_keeps_everything(self) -> None:
        event = message_created(TENANT, "c1", "u1")
        assert Event.from_json(event.to_json()) == event

    @pytest.mark.parametrize(
        "raw",
        [
            "not json",
            "[]",
            "{}",
            json.dumps({"type": "message.created", "tenant_id": TENANT, "audience": "everyone"}),
            json.dumps(
                {"type": "message.created", "tenant_id": TENANT, "audience": "staff", "data": {"text": "leak"}}
            ),
        ],
    )
    def test_a_forged_or_malformed_payload_is_rejected(self, raw: str) -> None:
        with pytest.raises(InvalidEvent):
            Event.from_json(raw)


class TestAudience:
    def test_other_tenants_never_match(self) -> None:
        for event in (
            job_updated(TENANT, "j", "d"),
            message_created(TENANT, "c", "u"),
            escalation_changed(TENANT, "c"),
        ):
            for role in ("user", "agent", "admin"):
                assert not visible_to(viewer(role, tenant=OTHER_TENANT), event)

    def test_job_and_document_events_go_to_admins_only(self) -> None:
        for event in (job_updated(TENANT, "j", "d"), document_changed(TENANT, "d")):
            assert visible_to(viewer("admin"), event)
            assert not visible_to(viewer("agent"), event)
            assert not visible_to(viewer("user"), event)

    def test_escalation_changes_go_to_staff_only(self) -> None:
        event = escalation_changed(TENANT, "c1")
        assert visible_to(viewer("admin"), event) and visible_to(viewer("agent"), event)
        assert not visible_to(viewer("user"), event)

    def test_conversation_events_go_to_the_owner_and_staff(self) -> None:
        owner = viewer("user")
        stranger = viewer("user")
        for event in (
            message_created(TENANT, "c1", owner.user_id),
            conversation_updated(TENANT, "c1", owner.user_id),
        ):
            assert visible_to(owner, event)
            assert not visible_to(stranger, event)
            assert visible_to(viewer("agent"), event) and visible_to(viewer("admin"), event)

    def test_a_conversation_without_a_known_owner_reaches_staff_only(self) -> None:
        event = message_created(TENANT, "c1", None)
        assert not visible_to(viewer("user"), event)
        assert visible_to(viewer("agent"), event)


class TestHub:
    async def test_dispatch_applies_the_filter(self) -> None:
        hub = EventHub()
        owner, stranger = viewer("user"), viewer("user")
        with hub.subscribe(owner) as mine, hub.subscribe(stranger) as theirs:
            hub.dispatch(message_created(TENANT, "c1", owner.user_id))
            assert (await mine.get(timeout=0.1)) is not None
            assert await theirs.get(timeout=0.05) is None

    async def test_the_per_user_cap_is_enforced_and_released(self) -> None:
        hub = EventHub(max_streams_per_user=2)
        me = viewer("user")
        with hub.subscribe(me), hub.subscribe(me):
            with pytest.raises(TooManyStreams):
                with hub.subscribe(me):
                    pass
            with hub.subscribe(viewer("user")):  # another user is unaffected
                pass
        with hub.subscribe(me):  # slots were released
            assert hub.streams_for(me.user_id) == 1
        assert hub.size == 0

    async def test_an_overflowing_queue_is_dropped_and_becomes_one_resync(self) -> None:
        hub = EventHub(queue_size=3)
        admin = viewer("admin")
        with hub.subscribe(admin) as sub:
            for n in range(10):
                hub.dispatch(document_changed(TENANT, f"d{n}"))
            assert await sub.get(timeout=0.1) is RESYNC_MARKER
            assert await sub.get(timeout=0.05) is None  # the backlog was dropped, not delivered late
            hub.dispatch(document_changed(TENANT, "after"))
            event = await sub.get(timeout=0.1)
            assert isinstance(event, Event) and event.data == {"document_id": "after"}

    async def test_resync_all_reaches_every_stream(self) -> None:
        hub = EventHub()
        with hub.subscribe(viewer()) as a, hub.subscribe(viewer("admin")) as b:
            hub.resync_all()
            assert await a.get(timeout=0.1) is RESYNC_MARKER
            assert await b.get(timeout=0.1) is RESYNC_MARKER

    async def test_a_slow_subscriber_does_not_hold_up_the_others(self) -> None:
        hub = EventHub(queue_size=2)
        with hub.subscribe(viewer("admin")) as slow, hub.subscribe(viewer("admin")) as fast:
            for n in range(5):
                hub.dispatch(document_changed(TENANT, f"d{n}"))
                await fast.get(timeout=0.1) if n < 2 else None
            assert await slow.get(timeout=0.1) is RESYNC_MARKER


class TestBus:
    async def test_the_memory_bus_publishes_to_subscribers(self) -> None:
        bus = InMemoryEventBus()
        admin = viewer("admin")
        with bus.subscription(admin) as sub:
            await bus.publish(document_changed(TENANT, "d1"))
            event = await sub.get(timeout=0.1)
        assert isinstance(event, Event) and event.type == "document.changed"

    async def test_publish_safely_never_raises(self) -> None:
        class Broken:
            async def publish(self, event: Event) -> None:
                raise RuntimeError("database is down")

        await publish_safely(Broken(), document_changed(TENANT, "d1"))
        await publish_safely(None, document_changed(TENANT, "d1"))

    async def test_the_postgres_listener_drops_an_invalid_notification(self) -> None:
        bus = PostgresEventBus(database=None, conninfo="")  # type: ignore[arg-type]  # delivery needs no database
        admin = viewer("admin")
        with bus.subscription(admin) as sub:
            bus.deliver("{broken")
            bus.deliver(
                json.dumps(
                    {"type": "document.changed", "tenant_id": TENANT, "audience": "admins", "data": {"title": "x"}}
                )
            )
            assert await sub.get(timeout=0.05) is None
            bus.deliver(document_changed(TENANT, "d1").to_json())
            assert isinstance(await sub.get(timeout=0.1), Event)


class FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


async def collect(frames, count: int):  # type: ignore[no-untyped-def]
    out = []
    async for frame in frames:
        out.append(frame_parts(frame.strip("\n")) if not frame.startswith(":") else (":", frame))
        if len(out) == count:
            break
    return out


class TestFrames:
    async def test_the_stream_starts_with_ready_then_carries_events(self) -> None:
        sub = Subscription(viewer("admin"), 10)
        frames = event_frames(sub, expires_at=asyncio.get_running_loop().time() + 10_000, clock=lambda: 0.0)
        sub.offer(document_changed(TENANT, "d1"))
        got = await collect(frames, 2)
        assert got == [("ready", {}), ("document.changed", {"document_id": "d1"})]

    async def test_an_idle_stream_sends_pings(self) -> None:
        sub = Subscription(viewer("admin"), 10)
        frames = event_frames(sub, expires_at=1e12, heartbeat_seconds=0.05, clock=lambda: 0.0)
        got = await collect(frames, 3)
        assert got[0][0] == "ready" and got[1][0] == ":" and got[2][0] == ":"

    async def test_an_overflowed_queue_sends_resync_and_the_stream_stays_open(self) -> None:
        sub = Subscription(viewer("admin"), 1)
        sub.offer(document_changed(TENANT, "d1"))
        sub.offer(document_changed(TENANT, "d2"))
        frames = event_frames(sub, expires_at=1e12, clock=lambda: 0.0)
        got = await collect(frames, 2)
        assert got == [("ready", {}), ("resync", {})]
        sub.offer(document_changed(TENANT, "d3"))
        assert (await collect(frames, 1)) == [("document.changed", {"document_id": "d3"})]

    async def test_the_stream_ends_with_reauth_at_token_expiry(self) -> None:
        sub = Subscription(viewer("admin"), 10)
        clock = FakeClock(100.0)
        frames = event_frames(sub, expires_at=100.2, heartbeat_seconds=60, clock=clock)
        assert frame_parts((await frames.__anext__()).strip("\n"))[0] == "ready"

        async def advance() -> None:
            await asyncio.sleep(0.05)
            clock.now = 101.0

        waiter = asyncio.create_task(advance())
        reauth = await asyncio.wait_for(frames.__anext__(), 2)
        await waiter
        assert frame_parts(reauth.strip("\n")) == ("reauth", {})
        with pytest.raises(StopAsyncIteration):
            await frames.__anext__()

    async def test_an_already_expired_token_gets_ready_then_reauth(self) -> None:
        sub = Subscription(viewer(), 10)
        frames = event_frames(sub, expires_at=5.0, clock=lambda: 10.0)
        assert [frame_parts(f.strip("\n"))[0] async for f in frames] == ["ready", "reauth"]
