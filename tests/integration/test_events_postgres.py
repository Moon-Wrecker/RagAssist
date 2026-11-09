"""PostgreSQL LISTEN/NOTIFY event bus with two listeners (two API processes) and a publisher-only worker.

Shows against a real database that: an event published by the worker reaches the matching subscribers of every API
process and nobody else; ``pg_notify`` is transactional (nothing before the commit, nothing after a rollback); and a
lost listener connection is re-opened and announced to the streams with ``resync``.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Callable
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ragassist.platform.events import Event, Viewer, document_changed, message_created
from ragassist.platform.events.adapters.postgres import (
    APPLICATION_NAME,
    PostgresEventBus,
    PostgresEventPublisher,
)
from ragassist.platform.events.hub import RESYNC_MARKER
from ragassist.shared.db.scoped import ScopedDatabase

from .conftest import PgServer


@pytest.fixture(scope="session")
def event_loop_policy():  # type: ignore[no-untyped-def]
    """psycopg's async mode needs the selector loop on Windows (Linux uses the default one)."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


def conninfo(server: PgServer) -> str:
    return server.app_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture
async def db(app_engines: Callable[..., AsyncEngine]) -> ScopedDatabase:
    return ScopedDatabase(async_sessionmaker(app_engines(), expire_on_commit=False))


@pytest.fixture
async def buses(
    pg_server: PgServer, db: ScopedDatabase
) -> AsyncIterator[tuple[PostgresEventBus, PostgresEventBus]]:
    first = PostgresEventBus(db, conninfo(pg_server), probe_seconds=1.0)
    second = PostgresEventBus(db, conninfo(pg_server), probe_seconds=1.0)
    await first.start()
    await second.start()
    await first.wait_listening()
    await second.wait_listening()
    yield first, second
    await first.stop()
    await second.stop()


def viewer(tenant: object, role: str, user: object | None = None) -> Viewer:
    return Viewer(tenant_id=str(tenant), user_id=str(user or uuid4()), role=role)


async def next_event(sub, timeout: float = 5.0):  # type: ignore[no-untyped-def]
    return await sub.get(timeout=timeout)


class TestTwoListeners:
    async def test_a_worker_event_reaches_the_matching_subscribers_of_every_process(
        self, pg_server: PgServer, buses, db: ScopedDatabase
    ) -> None:
        tenant, other_tenant = uuid4(), uuid4()
        worker = PostgresEventPublisher(db)
        with (
            buses[0].subscription(viewer(tenant, "admin")) as admin_on_first,
            buses[1].subscription(viewer(tenant, "admin")) as admin_on_second,
            buses[1].subscription(viewer(tenant, "user")) as user_on_second,
            buses[0].subscription(viewer(other_tenant, "admin")) as foreign_admin,
        ):
            await worker.publish(document_changed(tenant, "doc-1"))

            for sub in (admin_on_first, admin_on_second):
                event = await next_event(sub)
                assert isinstance(event, Event) and event.data == {"document_id": "doc-1"}
            assert await user_on_second.get(timeout=0.3) is None, (
                "users do not receive document events"
            )
            assert await foreign_admin.get(timeout=0.3) is None, "another tenant never receives it"

    async def test_conversation_events_reach_the_owner_but_not_another_user(
        self, buses, db: ScopedDatabase
    ) -> None:
        tenant = uuid4()
        owner_id = uuid4()
        with (
            buses[0].subscription(viewer(tenant, "user", owner_id)) as owner,
            buses[1].subscription(viewer(tenant, "user")) as stranger,
        ):
            await buses[1].publish(message_created(tenant, "conv-1", owner_id))
            event = await next_event(owner)
            assert isinstance(event, Event) and event.data == {"conversation_id": "conv-1"}
            assert await stranger.get(timeout=0.3) is None


class TestTransactionalDelivery:
    async def test_nothing_is_delivered_before_the_commit(self, buses, db: ScopedDatabase) -> None:
        tenant = uuid4()
        with buses[0].subscription(viewer(tenant, "admin")) as sub:
            async with db.transaction():
                await buses[0].publish(document_changed(tenant, "doc-tx"))
                assert await sub.get(timeout=0.4) is None, "pg_notify must wait for the commit"
            event = await next_event(sub)
            assert isinstance(event, Event) and event.data == {"document_id": "doc-tx"}

    async def test_a_rolled_back_transaction_publishes_nothing(
        self, buses, db: ScopedDatabase
    ) -> None:
        tenant = uuid4()
        with buses[0].subscription(viewer(tenant, "admin")) as sub:
            with pytest.raises(RuntimeError):
                async with db.transaction():
                    await buses[0].publish(document_changed(tenant, "doc-rolled-back"))
                    raise RuntimeError("the business transaction failed")
            assert await sub.get(timeout=0.5) is None


class TestReconnect:
    async def test_a_lost_listener_connection_is_reopened_and_streams_get_resync(
        self, buses, db: ScopedDatabase, admin_engine: AsyncEngine
    ) -> None:
        tenant = uuid4()
        with buses[0].subscription(viewer(tenant, "admin")) as sub:
            async with admin_engine.connect() as conn:
                await conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = :name"
                    ),
                    {"name": APPLICATION_NAME},
                )
            assert await next_event(sub, timeout=15) is RESYNC_MARKER

            await buses[0].wait_listening(timeout=15)
            await buses[1].wait_listening(timeout=15)
            await PostgresEventPublisher(db).publish(document_changed(tenant, "after-reconnect"))
            while True:  # the other bus may have resynced too; skip markers until the real event
                event = await next_event(sub)
                if event is not RESYNC_MARKER:
                    break
            assert isinstance(event, Event) and event.data == {"document_id": "after-reconnect"}
