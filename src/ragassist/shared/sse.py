"""Server-Sent Events framing shared by every streaming endpoint.

Consulted: WHATWG Server-Sent Events specification (field names, multi-line data, ``:`` comment frames, a blank line
ends a frame) https://html.spec.whatwg.org/multipage/server-sent-events.html. The assistant stream and the live
events stream both use these helpers so the wire format cannot drift between them.
"""

from __future__ import annotations

import json
from typing import Any

SSE_HEADERS: dict[str, str] = {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

#: Idle interval after which a stream sends a ``: ping`` comment so proxies keep the connection open.
HEARTBEAT_SECONDS = 15.0

PING_FRAME = ": ping\n\n"


def format_sse_frame(event: str, data: Any, event_id: str | None = None, retry: int | None = None) -> str:
    """Format a single SSE frame according to the WHATWG EventSource specification."""
    lines: list[str] = [f"event: {event}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if retry is not None:
        lines.append(f"retry: {retry}")

    if isinstance(data, str):
        try:
            json.loads(data)
            payload = data
        except (ValueError, TypeError):
            payload = json.dumps(data)
    else:
        payload = json.dumps(data)

    for data_line in payload.split("\n"):
        lines.append(f"data: {data_line}")
    lines.append("\n")
    return "\n".join(lines)
