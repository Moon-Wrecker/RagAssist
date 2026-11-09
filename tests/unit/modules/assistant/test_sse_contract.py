"""The SSE contract (plan section 7, docs/api/sse-contract.md): headers, event names and order,
heartbeat, disconnect, error and interrupt frames, and tenant-safe 404s on conversations.

Frame-level tests run the planned ``sse_stream`` over a scripted event source. Route-level tests run
the real application over ASGI and are PENDING until the assistant API is mounted.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from factories.principals import auth_header, make_token
from support.spec import SSE_EVENTS, SSE_HEARTBEAT_SECONDS
from support.specs import need
from support.specs.routes import concrete, require_route
from support.sse import parse_sse

from ragassist.main import create_app
from ragassist.shared.security.jwt import UserRole

ALLOWED_EVENTS = set(SSE_EVENTS) | {"error"}


async def scripted(events: list[dict]) -> AsyncIterator[dict]:
    for event in events:
        yield event


async def collect(stream: AsyncIterator[str]) -> str:
    return "".join([frame async for frame in stream])


class TestHeaders:
    def test_the_stream_headers_match_the_contract(self) -> None:
        headers = need("assistant.SSE_HEADERS")
        assert headers["Content-Type"].startswith("text/event-stream")
        assert headers["Cache-Control"] == "no-cache"
        assert headers["X-Accel-Buffering"] == "no"


class TestFrames:
    async def test_each_event_is_a_named_sse_frame_with_json_data(self) -> None:
        stream = need("assistant.sse_stream")(
            scripted([{"event": "token", "data": {"text": "Hi"}}, {"event": "done", "data": {}}]),
            heartbeat_seconds=60,
        )
        parsed = parse_sse(await collect(stream))
        assert parsed.names() == ["token", "done"]
        assert parsed.of("token")[0].json() == {"text": "Hi"}

    async def test_event_names_are_from_the_contract(self) -> None:
        stream = need("assistant.sse_stream")(
            scripted(
                [
                    {"event": "token", "data": {"text": "a"}},
                    {"event": "citation", "data": {"chunk_id": "c"}},
                    {"event": "done", "data": {}},
                ]
            ),
            heartbeat_seconds=60,
        )
        assert set(parse_sse(await collect(stream)).names()) <= ALLOWED_EVENTS

    async def test_done_is_the_last_event(self) -> None:
        stream = need("assistant.sse_stream")(
            scripted(
                [
                    {"event": "token", "data": {"text": "a"}},
                    {"event": "citation", "data": {"chunk_id": "c"}},
                    {"event": "done", "data": {}},
                ]
            ),
            heartbeat_seconds=60,
        )
        assert parse_sse(await collect(stream)).names()[-1] == "done"

    async def test_citations_arrive_before_done(self) -> None:
        stream = need("assistant.sse_stream")(
            scripted(
                [
                    {"event": "token", "data": {"text": "a"}},
                    {"event": "citation", "data": {"chunk_id": "c"}},
                    {"event": "done", "data": {}},
                ]
            ),
            heartbeat_seconds=60,
        )
        names = parse_sse(await collect(stream)).names()
        assert names.index("citation") < names.index("done")

    async def test_an_interrupt_frame_carries_the_interrupt_id(self) -> None:
        stream = need("assistant.sse_stream")(
            scripted(
                [
                    {
                        "event": "interrupt",
                        "data": {"interrupt_id": "int-1", "tool": "update_billing_email"},
                    }
                ]
            ),
            heartbeat_seconds=60,
        )
        (event,) = parse_sse(await collect(stream)).of("interrupt")
        assert event.json()["interrupt_id"] == "int-1"

    async def test_an_error_frame_is_well_formed_and_leaks_no_traceback(self) -> None:
        async def failing() -> AsyncIterator[dict]:
            yield {"event": "token", "data": {"text": "a"}}
            raise RuntimeError("provider exploded with secret sk-abc123")

        stream = need("assistant.sse_stream")(failing(), heartbeat_seconds=60)
        text = await collect(stream)
        (error,) = parse_sse(text).of("error")
        payload = error.json()
        assert payload.get("code") and "message" in payload
        assert "Traceback" not in text and "sk-abc123" not in text, "errors must not leak internals"

    async def test_an_unknown_event_name_is_rejected_not_forwarded(self) -> None:
        stream = need("assistant.sse_stream")(
            scripted([{"event": "not_a_contract_event", "data": {}}]), heartbeat_seconds=60
        )
        names = parse_sse(await collect(stream)).names()
        assert "not_a_contract_event" not in names


class TestHeartbeat:
    async def test_an_idle_stream_sends_a_ping_comment(self) -> None:
        async def idle() -> AsyncIterator[dict]:
            await asyncio.sleep(10)
            yield {"event": "done", "data": {}}

        stream = need("assistant.sse_stream")(idle(), heartbeat_seconds=0.05)
        first = await asyncio.wait_for(stream.__anext__(), timeout=2)
        assert first.lstrip().startswith(":"), "an idle connection needs a keep-alive comment"

    async def test_the_heartbeat_interval_is_the_contract_value(self) -> None:
        assert SSE_HEARTBEAT_SECONDS == 15


class TestDisconnect:
    async def test_closing_the_stream_closes_the_source(self) -> None:
        closed: list[bool] = []

        async def source() -> AsyncIterator[dict]:
            try:
                while True:
                    yield {"event": "token", "data": {"text": "x"}}
                    await asyncio.sleep(0)
            finally:
                closed.append(True)

        stream = need("assistant.sse_stream")(source(), heartbeat_seconds=60)
        await stream.__anext__()
        await stream.aclose()
        assert closed == [True], "a client disconnect must cancel the graph run"


class TestRoutes:
    @pytest.fixture
    def app(self):  # type: ignore[no-untyped-def]
        return create_app()

    @pytest.fixture
    def headers(self):  # type: ignore[no-untyped-def]
        return auth_header(make_token(role=UserRole.USER))

    async def test_the_ask_route_streams_with_the_contract_headers(self, app, headers) -> None:  # type: ignore[no-untyped-def]
        method, path = require_route(app, "ask_message")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api.test"
        ) as client:
            async with client.stream(
                method,
                concrete(path),
                json={"content": "hi"},
                headers={**headers, "Accept": "text/event-stream"},
            ) as response:
                assert response.headers["content-type"].startswith("text/event-stream")
                assert response.headers["cache-control"] == "no-cache"
                assert response.headers["x-accel-buffering"] == "no"

    async def test_the_ask_route_requires_a_token(self, app) -> None:  # type: ignore[no-untyped-def]
        method, path = require_route(app, "ask_message")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api.test"
        ) as client:
            response = await client.request(method, concrete(path), json={"content": "hi"})
        assert response.status_code in (401, 403)

    async def test_an_unknown_or_foreign_conversation_is_a_404_not_a_403(self, app) -> None:  # type: ignore[no-untyped-def]
        method, path = require_route(app, "ask_message")
        other_tenant = auth_header(make_token(role=UserRole.USER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api.test"
        ) as client:
            response = await client.request(
                method, concrete(path), json={"content": "hi"}, headers=other_tenant
            )
        assert response.status_code == 404, "a foreign conversation must look like a missing one"
