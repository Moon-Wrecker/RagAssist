"""Minimal, spec-faithful Server-Sent-Events parser for tests.

Follows the WHATWG event-stream rules we rely on: ``event:``, ``data:`` (multi-line joined with
``\\n``), ``id:``, ``retry:``, comment lines (``: ping``) used as heartbeats, blank line ends an
event, CRLF / LF / CR line endings accepted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SSEEvent:
    event: str = "message"
    data: str = ""
    id: str | None = None
    retry: int | None = None

    def json(self) -> Any:
        return json.loads(self.data)


class CallableList(list):
    def __call__(self) -> list:
        return self


@dataclass
class SSEStream:
    events: list[SSEEvent] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    @property
    def names(self) -> CallableList:
        return CallableList([e.event for e in self.events])

    def of(self, name: str) -> list[SSEEvent]:
        return [e for e in self.events if e.event == name]


def parse_sse(text: str) -> SSEStream:
    """Parse a complete SSE payload into events and heartbeat comments."""
    stream = SSEStream()
    current = SSEEvent()
    data_lines: list[str] = []
    has_content = False

    def flush() -> None:
        nonlocal current, data_lines, has_content
        if has_content:
            current.data = "\n".join(data_lines)
            stream.events.append(current)
        current = SSEEvent()
        data_lines = []
        has_content = False

    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    for line in normalised.split("\n"):
        if line == "":
            flush()
            continue
        if line.startswith(":"):
            stream.comments.append(line[1:].strip())
            continue
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "event":
            current.event = value
            has_content = True
        elif name == "data":
            data_lines.append(value)
            has_content = True
        elif name == "id":
            current.id = value
            has_content = True
        elif name == "retry" and value.isdigit():
            current.retry = int(value)
            has_content = True
    flush()
    return stream
