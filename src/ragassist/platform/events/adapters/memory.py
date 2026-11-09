"""In-memory event bus: publishing dispatches straight to this process's subscribers."""

from __future__ import annotations

from contextlib import AbstractContextManager

from ragassist.platform.events.hub import EventHub, Subscription
from ragassist.platform.events.model import Event, Viewer


class InMemoryEventBus:
    """Single-process bus used by the memory backend and the tests."""

    def __init__(self, *, queue_size: int = 100, max_streams_per_user: int = 5) -> None:
        self.hub = EventHub(queue_size=queue_size, max_streams_per_user=max_streams_per_user)
        self.published: list[Event] = []

    async def publish(self, event: Event) -> None:
        self.published.append(event)
        self.hub.dispatch(event)

    def subscription(self, viewer: Viewer) -> AbstractContextManager[Subscription]:
        return self.hub.subscribe(viewer)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None
