"""Drive an ASGI app by hand so a test can read a streaming response chunk by chunk and disconnect mid-stream.

``httpx.ASGITransport`` buffers the whole response, so it cannot show that frames are flushed while the stream is
still open, nor that a client disconnect reaches the endpoint through the middleware stack. This driver can.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any


class AsgiCall:
    def __init__(
        self,
        app: Any,
        path: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        client: tuple[str, int] = ("asgi.test", 50000),
    ) -> None:
        raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
        if body:
            raw_headers.append((b"content-length", str(len(body)).encode()))
        self._scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": raw_headers,
            "client": client,
            "server": ("api.test", 80),
        }
        self._app = app
        self._body = body
        self._request_sent = False
        self._disconnect = asyncio.Event()
        self._chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self._started = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def _receive(self) -> dict[str, Any]:
        if not self._request_sent:
            self._request_sent = True
            return {"type": "http.request", "body": self._body, "more_body": False}
        await self._disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = {k.decode().lower(): v.decode() for k, v in message.get("headers", [])}
            self._started.set()
        elif message["type"] == "http.response.body":
            if message.get("body"):
                self._chunks.put_nowait(message["body"])
            if not message.get("more_body", False):
                self._chunks.put_nowait(None)

    async def _run(self) -> None:
        try:
            await self._app(self._scope, self._receive, self._send)
        finally:
            self._started.set()
            self._chunks.put_nowait(None)

    async def start(self, timeout: float = 5.0) -> AsgiCall:
        self._task = asyncio.create_task(self._run())
        await asyncio.wait_for(self._started.wait(), timeout)
        return self

    async def chunk(self, timeout: float = 5.0) -> str | None:
        """The next body chunk as text, or ``None`` when the response has ended."""
        item = await asyncio.wait_for(self._chunks.get(), timeout)
        return None if item is None else item.decode()

    async def frames(self, count: int, timeout: float = 5.0) -> list[str]:
        """Read until ``count`` complete SSE frames (blank-line terminated) have arrived."""
        text = ""
        while text.count("\n\n") < count:
            piece = await self.chunk(timeout)
            if piece is None:
                break
            text += piece
        return [f for f in text.split("\n\n") if f]

    async def disconnect(self, timeout: float = 5.0) -> None:
        self._disconnect.set()
        if self._task is not None:
            await asyncio.wait_for(asyncio.shield(self._task), timeout)

    async def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

    @property
    def finished(self) -> bool:
        return self._task is not None and self._task.done()

    def json(self, chunk: str) -> Any:
        """Body of a non-streaming response chunk."""
        return json.loads(chunk)


def frame_parts(frame: str) -> tuple[str, Any]:
    """``(event name, data)`` of one SSE frame; a comment frame yields ``(":", text)``."""
    if frame.startswith(":"):
        return ":", frame
    event = ""
    data = ""
    for line in frame.splitlines():
        if line.startswith("event: "):
            event = line[len("event: ") :]
        elif line.startswith("data: "):
            data += line[len("data: ") :]
    return event, json.loads(data) if data else None
