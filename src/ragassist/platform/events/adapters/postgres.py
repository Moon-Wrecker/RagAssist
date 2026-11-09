"""PostgreSQL ``LISTEN``/``NOTIFY`` event bus (ADR 0008).

Goal: let the API and the worker announce changes through the database they already share, with no extra broker.

* Publishing is ``SELECT pg_notify(channel, payload)`` inside a ``ScopedDatabase`` scope. ``pg_notify`` is
  transactional: inside ``database.transaction()`` the notification is delivered only after the commit, so a client
  that refetches on the event always sees the committed rows. Outside a transaction it commits immediately.
* Listening happens on **one** dedicated psycopg connection per API process, which fans events out to the bounded
  per-subscriber queues of the in-process ``EventHub``. A lost connection is re-opened with backoff; because events
  were possibly missed meanwhile, every successful reconnect sends ``resync`` to all streams.

Consulted: PostgreSQL docs for ``LISTEN``/``NOTIFY`` (payload limit, delivery at commit, one notification per
distinct payload per transaction) https://www.postgresql.org/docs/current/sql-notify.html; psycopg 3 "Asynchronous
notifications" (``AsyncConnection.notifies(timeout=...)``) https://www.psycopg.org/psycopg3/docs/advanced/async.html.
The listener runs on a psycopg connection because asyncpg is not used for it; on Windows it needs the selector event
loop, exactly like the LangGraph checkpointer (``runtime.build_checkpointer`` fails fast with a clear message).
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import AbstractContextManager

import structlog
from sqlalchemy import text

from ragassist.platform.events.hub import EventHub, Subscription
from ragassist.platform.events.model import Event, InvalidEvent, Viewer
from ragassist.shared.db.scoped import ScopedDatabase

logger = structlog.get_logger(__name__)

#: Fixed identifier (never user input), so it is safe to splice into ``LISTEN``.
CHANNEL = "ragassist_events"
#: Label of the listener connection in ``pg_stat_activity``.
APPLICATION_NAME = "ragassist-events"

#: The listener probes the connection with ``SELECT 1`` at this interval, which also detects a dead socket.
LISTENER_PROBE_SECONDS = 30.0
RECONNECT_BACKOFF_START = 0.5
RECONNECT_BACKOFF_MAX = 10.0

_PUBLISH = text("SELECT pg_notify(:channel, :payload)")


class PostgresEventPublisher:
    """Publish-only side, used by the worker (it serves no streams)."""

    def __init__(self, database: ScopedDatabase) -> None:
        self._db = database

    async def publish(self, event: Event) -> None:
        async with self._db.scope(event.tenant_id) as session:
            await session.execute(_PUBLISH, {"channel": CHANNEL, "payload": event.to_json()})


class PostgresEventBus(PostgresEventPublisher):
    """Publisher plus the per-process listener and fan-out."""

    def __init__(
        self,
        database: ScopedDatabase,
        conninfo: str,
        *,
        queue_size: int = 100,
        max_streams_per_user: int = 5,
        probe_seconds: float = LISTENER_PROBE_SECONDS,
    ) -> None:
        super().__init__(database)
        self._conninfo = conninfo
        self._probe_seconds = probe_seconds
        self.hub = EventHub(queue_size=queue_size, max_streams_per_user=max_streams_per_user)
        self._task: asyncio.Task[None] | None = None
        self._listening = asyncio.Event()
        self._connected_before = False

    # -- bus port ---------------------------------------------------------------------------------------------
    def subscription(self, viewer: Viewer) -> AbstractContextManager[Subscription]:
        return self.hub.subscribe(viewer)

    async def start(self, *, wait_seconds: float = 5.0) -> None:
        """Start the listener task and give it a moment to establish ``LISTEN`` (not fatal if it takes longer)."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="events-listener")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._listening.wait(), wait_seconds)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def wait_listening(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._listening.wait(), timeout)

    # -- listener ---------------------------------------------------------------------------------------------
    def deliver(self, payload: str) -> None:
        """Fan one notification out to the subscribers; a malformed payload is dropped."""
        try:
            event = Event.from_json(payload)
        except InvalidEvent:
            logger.warning("events.invalid_payload_dropped")
            return
        self.hub.dispatch(event)

    async def _run(self) -> None:
        import psycopg

        backoff = RECONNECT_BACKOFF_START
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    self._conninfo, autocommit=True, application_name=APPLICATION_NAME
                ) as conn:
                    await conn.execute(f"LISTEN {CHANNEL}")
                    if self._connected_before:
                        # Notifications sent while we were away are gone: every stream refetches everything.
                        self.hub.resync_all()
                    self._connected_before = True
                    self._listening.set()
                    backoff = RECONNECT_BACKOFF_START
                    while True:
                        async for notification in conn.notifies(timeout=self._probe_seconds):
                            self.deliver(notification.payload)
                        await conn.execute("SELECT 1")  # raises when the connection is dead
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure means: wait, reconnect, resync
                self._listening.clear()
                logger.warning("events.listener_lost", error=str(exc), retry_in=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX)
