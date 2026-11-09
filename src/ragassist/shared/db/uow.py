"""UnitOfWork pattern with strict PostgreSQL Row-Level Security (RLS) enforcement."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from ragassist.shared.db.session import get_session_factory
from ragassist.shared.domain import TenantId, TenantIsolationError

logger = structlog.get_logger(__name__)


class UnitOfWork:
    """Manages transactional boundaries and sets PostgreSQL RLS context."""

    def __init__(self, session: AsyncSession, tenant_id: TenantId | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self._in_transaction = False

    async def __aenter__(self) -> "UnitOfWork":
        """Begin transaction and set RLS session context."""
        if not self.session.in_transaction():
            await self.session.begin()
        self._in_transaction = True

        if self.tenant_id is not None:
            # SET LOCAL ensures the setting is strictly scoped to this transaction
            # and automatically rolls back / resets when the transaction commits or aborts.
            # is_local=true protects connection pools from tenant state bleeding.
            query = text("SELECT set_config('app.tenant_id', :tid, true)")
            await self.session.execute(query, {"tid": str(self.tenant_id)})
            logger.debug("rls.set_local_tenant", tenant_id=str(self.tenant_id))
        else:
            # Clear or default to null for system/admin operations
            query = text("SELECT set_config('app.tenant_id', '', true)")
            await self.session.execute(query)

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Commit or rollback transaction cleanly."""
        try:
            if exc_type is not None:
                await self.rollback()
            else:
                await self.commit()
        finally:
            self._in_transaction = False

    async def commit(self) -> None:
        """Commit the current transaction."""
        if self._in_transaction:
            await self.session.commit()

    async def rollback(self) -> None:
        """Roll back the current transaction."""
        if self._in_transaction:
            await self.session.rollback()


@asynccontextmanager
async def tenant_uow(tenant_id: TenantId) -> AsyncGenerator[UnitOfWork, None]:
    """Context manager providing a UnitOfWork scoped to a verified tenant."""
    if not tenant_id:
        raise TenantIsolationError("Cannot establish UnitOfWork without a valid TenantId.")
    factory = get_session_factory()
    async with factory() as session:
        async with UnitOfWork(session, tenant_id) as uow:
            yield uow

