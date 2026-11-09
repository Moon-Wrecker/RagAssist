"""Live change notifications (ADR 0008): ports, model, fan-out hub and the process-wide bus accessor."""

from __future__ import annotations

from ragassist.platform.events.adapters.memory import InMemoryEventBus
from ragassist.platform.events.hub import EventHub, Subscription, TooManyStreams
from ragassist.platform.events.model import (
    Audience,
    Event,
    InvalidEvent,
    Viewer,
    conversation_updated,
    document_changed,
    escalation_changed,
    job_updated,
    message_created,
    visible_to,
)
from ragassist.platform.events.ports import EventBus, EventPublisher, publish_safely

__all__ = [
    "Audience",
    "Event",
    "EventBus",
    "EventHub",
    "EventPublisher",
    "InMemoryEventBus",
    "InvalidEvent",
    "Subscription",
    "TooManyStreams",
    "Viewer",
    "conversation_updated",
    "document_changed",
    "escalation_changed",
    "get_event_bus",
    "job_updated",
    "message_created",
    "publish_safely",
    "visible_to",
]

_memory_bus: InMemoryEventBus | None = None


def get_event_bus() -> EventBus:
    """The Postgres bus when the runtime is started (PERSISTENCE_BACKEND=postgres), else one in-memory bus."""
    from ragassist.runtime import active_runtime

    runtime = active_runtime()
    if runtime is not None:
        return runtime.events
    global _memory_bus
    if _memory_bus is None:
        from ragassist.shared.config.settings import get_settings

        settings = get_settings()
        _memory_bus = InMemoryEventBus(
            queue_size=settings.EVENTS_QUEUE_SIZE,
            max_streams_per_user=settings.EVENTS_MAX_STREAMS_PER_USER,
        )
    return _memory_bus


def reset_memory_event_bus() -> None:
    """Forget the in-memory bus (test isolation)."""
    global _memory_bus
    _memory_bus = None
