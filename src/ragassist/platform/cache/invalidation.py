"""Invalidate a tenant's cached retrieval when its documents change (ADR 0015).

The signal is the one that already exists: ``document.changed`` on the events bus (ADR 0008). The API publishes it
when a document is uploaded, re-indexed or deleted, and the ingestion worker publishes it after the new chunks are
committed (through ``pg_notify``, which every API process hears). Each process attaches an observer to its event
hub, so the signal reaches every process's cache without a second channel; with Redis one process is enough and the
others repeat an idempotent invalidation.

Events carry ids only, so the observer needs nothing but the tenant id from the event itself.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import structlog

from ragassist.platform.cache.service import CacheService
from ragassist.platform.events.hub import EventHub
from ragassist.platform.events.model import DOCUMENT_CHANGED, Event

logger = structlog.get_logger(__name__)

_pending: set[asyncio.Task[None]] = set()


def install_corpus_invalidation(hub: EventHub, service: Callable[[], CacheService]) -> None:
    """Attach the observer to ``hub``. ``service`` is resolved per event, so a rebuilt cache is never bypassed."""

    def on_event(event: Event) -> None:
        if event.type != DOCUMENT_CHANGED:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # dispatched outside an event loop: nothing can be awaited, TTL still bounds it
            return
        task = loop.create_task(_invalidate(service(), event.tenant_id), name="cache-invalidate")
        _pending.add(task)
        task.add_done_callback(_pending.discard)

    hub.add_observer(on_event)


async def _invalidate(service: CacheService, tenant_id: str) -> None:
    try:
        await service.invalidate_corpus(tenant_id)
    except Exception as exc:  # noqa: BLE001 - the TTL bounds staleness if this fails
        logger.warning("cache.invalidation_failed", error=type(exc).__name__)


async def settle() -> None:
    """Wait for invalidations already scheduled (tests, orderly shutdown)."""
    if _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
