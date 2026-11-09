"""``GET /v1/events``: the long-lived SSE stream of change notifications (ADR 0008, docs/api/sse-contract.md).

Goal: tell a signed-in client *that* something changed (type and ids only) so it refetches through the normal API.

Behaviour: the stream is tied to the verified principal (tenant, user, role come from the JWT only) and filters on the
server; it ends with ``reauth`` at the expiry of the access token it was opened with; a dropped queue or a lost
database listener produces ``resync``; a user may hold a limited number of streams.

Consulted: Starlette ``StreamingResponse`` (client disconnect cancels the generator, so ``finally`` releases the
subscription), WHATWG SSE specification, docs/api/sse-contract.md.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ragassist.platform.events import TooManyStreams, get_event_bus
from ragassist.platform.events.hub import RESYNC_MARKER, Subscription
from ragassist.platform.events.model import READY, REAUTH, RESYNC, Event, Viewer
from ragassist.shared.security.deps import get_current_principal
from ragassist.shared.security.jwt import Principal, access_token_expiry
from ragassist.shared.sse import HEARTBEAT_SECONDS, PING_FRAME, SSE_HEADERS, format_sse_frame

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Events"])


class _ReleasingStream(StreamingResponse):
    """A streaming response that frees the subscription however the response ends (done, cancelled, disconnected)."""

    def __init__(self, content: AsyncIterator[str], release: Callable[[], None], **kwargs: Any) -> None:
        super().__init__(content, **kwargs)
        self._release = release

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._release()


async def event_frames(
    subscription: Subscription,
    *,
    expires_at: float,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    clock: Any = time.time,
) -> AsyncIterator[str]:
    """SSE frames for one stream: ``ready``, then events, pings while idle, ``reauth`` at ``expires_at`` (epoch seconds)."""
    yield format_sse_frame(READY, {})
    while True:
        remaining = expires_at - clock()
        if remaining <= 0:
            yield format_sse_frame(REAUTH, {})
            return
        item = await subscription.get(timeout=min(heartbeat_seconds, remaining))
        if item is None:
            if expires_at - clock() <= 0:
                yield format_sse_frame(REAUTH, {})
                return
            yield PING_FRAME
        elif item is RESYNC_MARKER:
            yield format_sse_frame(RESYNC, {})
        elif isinstance(item, Event):
            yield format_sse_frame(item.type, item.payload())


@router.get(
    "/events",
    summary="Live change notifications (SSE)",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "Server-Sent Events: `ready`, `job.updated`, `document.changed`, `message.created`, "
                "`conversation.updated`, `escalation.changed`, `resync`, `reauth`. Payloads carry ids only."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        429: {"description": "Too many open event streams for this user."},
    },
)
async def stream_events(
    principal: Principal = Depends(get_current_principal),
    bus: Any = Depends(get_event_bus),
) -> StreamingResponse:
    """Open the caller's event stream. Needs the bearer token, so use a fetch-based reader, not ``EventSource``."""
    expires_at = access_token_expiry(principal.raw_token)
    viewer = Viewer.from_principal(principal)
    manager = bus.subscription(viewer)
    try:
        subscription = manager.__enter__()
    except TooManyStreams as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many open event streams",
            headers={"Retry-After": "5"},
        ) from exc

    released = False

    def release() -> None:
        nonlocal released
        if not released:
            released = True
            manager.__exit__(None, None, None)

    async def body() -> AsyncIterator[str]:
        async for frame in event_frames(subscription, expires_at=expires_at):
            yield frame

    return _ReleasingStream(body(), release, headers=SSE_HEADERS, media_type="text/event-stream")
