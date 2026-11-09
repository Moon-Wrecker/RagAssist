"""Row-level-security scoped database access shared by every Postgres repository.

Goal: give each repository one primitive, ``scope(tenant_id)``, that yields an ``AsyncSession`` inside an explicit
transaction whose ``app.tenant_id`` is set with ``set_config(..., is_local => true)`` (AGENTS.md section 1.3).
Repositories never open sessions themselves, so a statement cannot run without a tenant context.

``transaction()`` groups several repository calls (for example "store the object, add the job, add the document,
enqueue the message") into one database transaction; calls made inside it reuse that transaction. Callbacks
registered with ``defer_until_commit`` run only after the commit succeeded, which keeps a queue message from being
received before the rows it refers to are visible to the worker.

Consulted: SQLAlchemy 2.0 asyncio (AsyncSession, async_sessionmaker), PostgreSQL ``set_config`` and row security
policies, and the existing ``UnitOfWork`` in ``shared/db/uow.py`` (the same ``set_config`` statement).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ragassist.shared.domain import TenantIsolationError

logger = structlog.get_logger(__name__)

SET_TENANT = text("SELECT set_config('app.tenant_id', :tid, true)")


@dataclass
class _Transaction:
    session: AsyncSession
    tenant: str | None = None
    bound: bool = False
    after_commit: list[Callable[[], Awaitable[Any]]] = field(default_factory=list)


class ScopedDatabase:
    """Opens tenant-scoped sessions on a session factory."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory
        self._current: ContextVar[_Transaction | None] = ContextVar("scoped_db_transaction", default=None)

    @asynccontextmanager
    async def scope(self, tenant_id: object | None) -> AsyncIterator[AsyncSession]:
        """Yield a session bound to ``tenant_id`` (``None`` = no tenant context: system access, global rows only)."""
        tenant = str(tenant_id) if tenant_id else ""
        tx = self._current.get()
        if tx is not None:
            if tx.bound and (tx.tenant or "") != tenant:
                raise TenantIsolationError("A transaction cannot span two tenants.")
            await tx.session.execute(SET_TENANT, {"tid": tenant})
            tx.tenant, tx.bound = tenant, True
            yield tx.session
            return
        async with self._factory() as session:
            async with session.begin():
                await session.execute(SET_TENANT, {"tid": tenant})
                yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Run the enclosed repository calls atomically; deferred callbacks run after a successful commit."""
        if self._current.get() is not None:
            raise RuntimeError("Transactions do not nest.")
        async with self._factory() as session:
            tx = _Transaction(session=session)
            token = self._current.set(tx)
            try:
                await session.begin()
                try:
                    yield
                except BaseException:
                    await session.rollback()
                    raise
                await session.commit()
            finally:
                self._current.reset(token)
        for callback in tx.after_commit:
            await callback()

    async def defer_until_commit(self, callback: Callable[[], Awaitable[Any]]) -> None:
        """Run ``callback`` after the surrounding transaction commits (immediately when there is none)."""
        tx = self._current.get()
        if tx is None:
            await callback()
        else:
            tx.after_commit.append(callback)
