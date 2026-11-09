"""Fake SQLAlchemy ``AsyncSession`` recording transaction operations.

Good for asserting *what the UnitOfWork asks the database to do*. It cannot prove RLS works: that
needs a real Postgres (tests/integration).
"""

from __future__ import annotations

from typing import Any


class FakeAsyncSession:
    def __init__(
        self,
        *,
        fail_on_begin: Exception | None = None,
        fail_on_commit: Exception | None = None,
    ) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.events: list[str] = []
        self._fail_on_begin = fail_on_begin
        self._fail_on_commit = fail_on_commit
        self._open = False

    # -- recorded state -------------------------------------------------------------------------
    @property
    def begun(self) -> bool:
        return "begin" in self.events

    @property
    def committed(self) -> bool:
        return "commit" in self.events

    @property
    def rolled_back(self) -> bool:
        return "rollback" in self.events

    @property
    def tenant_setting(self) -> str | None:
        """Last value passed to ``set_config('app.tenant_id', ...)``; None if never set."""
        for sql, params in reversed(self.statements):
            if "app.tenant_id" in sql:
                return str(params["tid"]) if "tid" in params else ""
        return None

    @property
    def app_tenant_setting(self) -> str | None:
        """Backwards-compatible alias of :attr:`tenant_setting` (used by tests/e2e)."""
        return self.tenant_setting

    # -- AsyncSession surface used by UnitOfWork ------------------------------------------------
    def in_transaction(self) -> bool:
        return self._open

    def open_transaction(self) -> None:
        """Simulate a transaction the caller already has open (an autobegun statement, an outer unit)."""
        self._open = True

    async def begin(self) -> None:
        self.events.append("begin")
        if self._fail_on_begin is not None:
            raise self._fail_on_begin
        self._open = True

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> None:
        self.events.append("execute")
        self.statements.append((str(statement), dict(params or {})))

    async def commit(self) -> None:
        self._open = False
        self.events.append("commit")
        if self._fail_on_commit is not None:
            raise self._fail_on_commit

    async def rollback(self) -> None:
        self._open = False
        self.events.append("rollback")
