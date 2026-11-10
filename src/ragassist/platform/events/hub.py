"""Per-process fan-out from one source of events to many bounded subscriber queues.

A slow client must not hold memory or block the rest: each subscription keeps at most ``queue_size`` events; when it
overflows, the queue is dropped and the next item the stream reads is a resync marker (the client refetches everything).
All methods run on the event loop thread, so no locking is needed.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from ragassist.platform.events.model import Event, Viewer, visible_to


class _Resync:
    """Marker item: events may have been lost, refetch everything."""

    def __repr__(self) -> str:
        return "RESYNC"


RESYNC_MARKER = _Resync()


class TooManyStreams(Exception):
    """The user already holds the maximum number of open streams."""


class Subscription:
    """One connected stream's bounded queue."""

    def __init__(self, viewer: Viewer, queue_size: int) -> None:
        self.viewer = viewer
        self._max = max(1, queue_size)
        self._items: deque[Event] = deque()
        self._wake = asyncio.Event()
        self._overflowed = False

    def offer(self, event: Event) -> None:
        """Queue an event; on overflow drop the queue and remember to send a resync."""
        if self._overflowed:
            return
        if len(self._items) >= self._max:
            self.request_resync()
            return
        self._items.append(event)
        self._wake.set()

    def request_resync(self) -> None:
        self._items.clear()
        self._overflowed = True
        self._wake.set()

    async def get(self, timeout: float | None = None) -> Event | _Resync | None:
        """The next event or the resync marker; ``None`` when ``timeout`` seconds pass with nothing."""
        while True:
            if self._overflowed:
                self._overflowed = False
                return RESYNC_MARKER
            if self._items:
                return self._items.popleft()
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout)
            except TimeoutError:
                return None


class EventHub:
    """Registry of subscriptions with the per-user cap, and the dispatch that applies the audience filter."""

    def __init__(self, *, queue_size: int = 100, max_streams_per_user: int = 5) -> None:
        self._queue_size = queue_size
        self._max_per_user = max_streams_per_user
        self._subscriptions: set[Subscription] = set()
        self._observers: list[Callable[[Event], None]] = []

    def add_observer(self, observer: Callable[[Event], None]) -> None:
        """Call ``observer(event)`` for every dispatched event, whatever the audience (for server-side reactions
        such as cache invalidation, never for delivery). It must be quick and must not raise; if it does, the
        failure is ignored so a broken observer cannot stop the events reaching the streams."""
        self._observers.append(observer)

    @property
    def size(self) -> int:
        return len(self._subscriptions)

    def streams_for(self, user_id: str) -> int:
        return sum(1 for s in self._subscriptions if s.viewer.user_id == user_id)

    @contextmanager
    def subscribe(self, viewer: Viewer) -> Iterator[Subscription]:
        if self.streams_for(viewer.user_id) >= self._max_per_user:
            raise TooManyStreams(viewer.user_id)
        sub = Subscription(viewer, self._queue_size)
        self._subscriptions.add(sub)
        try:
            yield sub
        finally:
            self._subscriptions.discard(sub)

    def dispatch(self, event: Event) -> None:
        """Deliver ``event`` to every subscription whose viewer may see it."""
        for observer in tuple(self._observers):
            try:
                observer(event)
            except Exception:  # noqa: BLE001, S110 - an observer is a hint, never a reason to drop an event
                pass
        for sub in tuple(self._subscriptions):
            if visible_to(sub.viewer, event):
                sub.offer(event)

    def resync_all(self) -> None:
        for sub in tuple(self._subscriptions):
            sub.request_resync()
