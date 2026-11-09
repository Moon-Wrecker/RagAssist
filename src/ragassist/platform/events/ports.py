"""Ports of the events platform: publish a change, subscribe to the changes a viewer may see."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

import structlog

from ragassist.platform.events.hub import Subscription
from ragassist.platform.events.model import Event, Viewer

logger = structlog.get_logger(__name__)


class EventPublisher(Protocol):
    """Anything that can announce a change (the API process, the worker)."""

    async def publish(self, event: Event) -> None: ...


class EventBus(EventPublisher, Protocol):
    """A publisher plus the per-process fan-out to connected streams."""

    def subscription(self, viewer: Viewer) -> AbstractContextManager[Subscription]:
        """Register a stream for ``viewer``; raises ``TooManyStreams`` over the per-user cap."""
        ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


async def publish_safely(publisher: EventPublisher | None, *events: Event) -> None:
    """Announce changes without ever failing the caller: the change is already committed, the event is a hint."""
    if publisher is None:
        return
    for event in events:
        try:
            await publisher.publish(event)
        except Exception as exc:  # noqa: BLE001 - a lost event only costs the client a refetch on its next resync
            logger.warning("events.publish_failed", event_type=event.type, error=str(exc))
