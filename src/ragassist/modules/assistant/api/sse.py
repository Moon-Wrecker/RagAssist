"""Server-Sent Events (SSE) streaming generator and headers.

Consulted References & Standards:
- WHATWG Server-Sent Events Specification (https://html.spec.whatwg.org/multipage/server-sent-events.html):
  - Field names: 'event:', 'data:', 'id:', 'retry:'.
  - Multiline data: payload lines are prefixed with 'data: '.
  - Comments: lines starting with ':' used as keepalive/heartbeat frames without triggering DOM events.
  - Frame termination: blank line ('\\n\\n') closes an event block.
- Starlette StreamingResponse & Disconnect Handling (https://www.starlette.io/responses/#streamingresponse):
  - Async generator stream with HTTP chunked transfer encoding.
  - Client disconnect triggers GeneratorExit or asyncio.CancelledError.
  - Disconnect handling must re-raise GeneratorExit/CancelledError and cancel underlying source coroutines.
- Nginx reverse-proxy buffering header: 'X-Accel-Buffering: no'.
- Python PEP 525 (Asynchronous Generators) for proper generator termination semantics.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from ragassist.shared.sse import SSE_HEADERS, format_sse_frame

__all__ = ["ALLOWED_EVENTS", "SSE_HEADERS", "format_sse_frame", "sse_stream"]

ALLOWED_EVENTS = frozenset({
    "token",
    "citation",
    "source",
    "tool_call",
    "interrupt",
    "escalated",
    "done",
    "error",
})


async def sse_stream(
    events: AsyncIterator[dict[str, Any]],
    *,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    """Stream events as SSE frames with periodic ping comments when idle.

    Closing the stream closes the source event generator cleanly.
    """
    next_task: asyncio.Task[Any] | None = None
    try:
        anext_coro = events.__anext__()
        next_task = asyncio.create_task(anext_coro)
        while True:
            try:
                event_item = await asyncio.wait_for(asyncio.shield(next_task), timeout=heartbeat_seconds)
                next_task = asyncio.create_task(events.__anext__())

                event_name = event_item.get("event", "message")
                if event_name not in ALLOWED_EVENTS:
                    continue

                event_data = event_item.get("data", {})
                event_id = event_item.get("id")
                retry = event_item.get("retry")

                yield format_sse_frame(event_name, event_data, event_id=event_id, retry=retry)

                if event_name == "done":
                    break

            except asyncio.TimeoutError:
                # Idle for heartbeat_seconds: send ping comment per WHATWG spec
                yield ": ping\n\n"

            except StopAsyncIteration:
                break

    except (GeneratorExit, asyncio.CancelledError):
        # PEP 525: GeneratorExit must not yield further frames
        raise
    except Exception:
        # Leak no tracebacks or internal keys in error message
        yield format_sse_frame("error", {"code": "internal_error", "message": "An error occurred during processing."})
    finally:
        if next_task is not None and not next_task.done():
            next_task.cancel()
            try:
                await next_task
            except (asyncio.CancelledError, GeneratorExit, StopAsyncIteration, Exception):
                pass
        if hasattr(events, "aclose"):
            try:
                await events.aclose()
            except (GeneratorExit, asyncio.CancelledError, Exception):
                pass
