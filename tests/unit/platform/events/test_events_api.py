"""``GET /v1/events`` through the real application and its middleware stack.

The driver reads the response chunk by chunk and can disconnect mid-stream, which shows what ``httpx.ASGITransport``
cannot: that frames reach the client while the stream is still open (the ``BaseHTTPMiddleware`` layers do not buffer
it), that a disconnect reaches the endpoint through them, and that the per-user cap and token expiry behave.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from factories.principals import auth_header, make_token
from support.asgi_stream import AsgiCall, frame_parts

from ragassist.main import create_app
from ragassist.platform.events import (
    document_changed,
    get_event_bus,
    message_created,
)
from ragassist.shared.config.settings import get_settings
from ragassist.shared.security.jwt import UserRole
from ragassist.shared.security.rate_limiter import RateLimitMiddleware, SlidingWindowRateLimiter

TENANT = uuid4()


@pytest.fixture
def app():  # type: ignore[no-untyped-def]
    return create_app()


def open_stream(app, role: UserRole = UserRole.ADMIN, **token_args):  # type: ignore[no-untyped-def]
    token = make_token(role=role, tenant_id=token_args.pop("tenant_id", TENANT), **token_args)
    return AsgiCall(app, "/v1/events", headers=auth_header(token))


async def wait_until(predicate, timeout: float = 3.0) -> None:  # type: ignore[no-untyped-def]
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


class TestStream:
    async def test_the_stream_has_the_contract_headers_and_starts_with_ready(self, app) -> None:  # type: ignore[no-untyped-def]
        call = await open_stream(app).start()
        try:
            assert call.status == 200
            assert call.headers["content-type"].startswith("text/event-stream")
            assert call.headers["cache-control"] == "no-store"
            assert call.headers["x-accel-buffering"] == "no"
            (first,) = await call.frames(1)
            assert frame_parts(first) == ("ready", {})
        finally:
            await call.close()

    async def test_events_are_flushed_while_the_stream_is_open(self, app) -> None:  # type: ignore[no-untyped-def]
        call = await open_stream(app).start()
        try:
            await call.frames(1)  # ready
            await get_event_bus().publish(document_changed(TENANT, "doc-1"))
            (frame,) = await call.frames(1, timeout=2)
            assert frame_parts(frame) == ("document.changed", {"document_id": "doc-1"})
            assert not call.finished, "the response must still be open (not buffered until it ends)"
        finally:
            await call.close()

    async def test_a_client_disconnect_reaches_the_endpoint_and_frees_the_slot(self, app) -> None:  # type: ignore[no-untyped-def]
        bus = get_event_bus()
        call = await open_stream(app).start()
        await call.frames(1)
        assert bus.hub.size == 1  # type: ignore[attr-defined]
        await call.disconnect()
        await wait_until(lambda: bus.hub.size == 0)  # type: ignore[attr-defined]

    async def test_another_tenants_events_do_not_reach_the_stream(self, app) -> None:  # type: ignore[no-untyped-def]
        call = await open_stream(app).start()
        try:
            await call.frames(1)
            await get_event_bus().publish(document_changed(uuid4(), "foreign"))
            await get_event_bus().publish(document_changed(TENANT, "mine"))
            (frame,) = await call.frames(1, timeout=2)
            assert frame_parts(frame)[1] == {"document_id": "mine"}
        finally:
            await call.close()

    async def test_the_stream_ends_with_reauth_when_the_access_token_expires(self, app) -> None:  # type: ignore[no-untyped-def]
        token = make_token(role=UserRole.USER, tenant_id=TENANT, expires_delta=timedelta(seconds=2))
        call = await AsgiCall(app, "/v1/events", headers=auth_header(token)).start()
        frames = await call.frames(2, timeout=5)
        assert [frame_parts(f)[0] for f in frames] == ["ready", "reauth"]
        assert await call.chunk(timeout=2) is None, "the server closes the stream after reauth"
        await call.close()

    async def test_an_expired_or_missing_token_never_opens_a_stream(self, app) -> None:  # type: ignore[no-untyped-def]
        for headers in ({}, auth_header(make_token(expires_delta=timedelta(seconds=-5)))):
            call = await AsgiCall(app, "/v1/events", headers=headers).start()
            assert call.status in (401, 403)
            await call.close()
        assert get_event_bus().hub.size == 0  # type: ignore[attr-defined]


class TestConnectionCap:
    async def test_streams_beyond_the_per_user_cap_are_refused_with_429(self, app) -> None:  # type: ignore[no-untyped-def]
        cap = get_settings().EVENTS_MAX_STREAMS_PER_USER
        user = uuid4()
        calls = [await open_stream(app, user_id=user).start() for _ in range(cap)]
        try:
            refused = await open_stream(app, user_id=user).start()
            assert refused.status == 429 and "retry-after" in refused.headers
            await refused.close()
            other = await open_stream(app).start()  # another user is not affected
            assert other.status == 200
            await other.close()
            await calls[0].disconnect()
            await wait_until(lambda: get_event_bus().hub.streams_for(str(user)) == cap - 1)  # type: ignore[attr-defined]
            again = await open_stream(app, user_id=user).start()
            assert again.status == 200
            await again.close()
        finally:
            for call in calls:
                await call.close()


class TestRateLimitExemption:
    async def test_the_events_path_is_exempt_from_the_per_address_limit(self) -> None:
        from fastapi import FastAPI

        tiny = FastAPI()

        @tiny.get("/v1/events")
        async def events() -> dict[str, str]:
            return {"ok": "yes"}

        @tiny.get("/v1/other")
        async def other() -> dict[str, str]:
            return {"ok": "yes"}

        tiny.add_middleware(
            RateLimitMiddleware, limiter=SlidingWindowRateLimiter(limit=1, window_seconds=60)
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=tiny), base_url="http://api.test"
        ) as client:
            assert [(await client.get("/v1/events")).status_code for _ in range(4)] == [200] * 4
            assert [(await client.get("/v1/other")).status_code for _ in range(2)] == [200, 429]


class TestPublishersViaTheApi:
    async def test_message_events_reach_the_owner_and_staff_only(self, app) -> None:  # type: ignore[no-untyped-def]
        owner_id, stranger_id = uuid4(), uuid4()
        owner = await open_stream(app, UserRole.USER, user_id=owner_id).start()
        stranger = await open_stream(app, UserRole.USER, user_id=stranger_id).start()
        agent = await open_stream(app, UserRole.AGENT).start()
        try:
            for call in (owner, stranger, agent):
                await call.frames(1)
            await get_event_bus().publish(message_created(TENANT, "conv-1", owner_id))
            assert frame_parts((await owner.frames(1, timeout=2))[0]) == (
                "message.created",
                {"conversation_id": "conv-1"},
            )
            assert frame_parts((await agent.frames(1, timeout=2))[0])[0] == "message.created"
            with pytest.raises(asyncio.TimeoutError):
                await stranger.chunk(timeout=0.3)
        finally:
            for call in (owner, stranger, agent):
                await call.close()
