"""UnitOfWork (feature 3): transaction boundaries and the RLS tenant context.

These tests assert what the UoW *asks the database to do*, using a recording fake session. That the
setting really isolates rows is proven against real Postgres in tests/integration.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from factories import new_tenant
from fakes import FakeAsyncSession

from ragassist.shared.db import uow as uow_module
from ragassist.shared.db.uow import UnitOfWork, tenant_uow
from ragassist.shared.domain import TenantId, TenantIsolationError


class TestTransactionBoundaries:
    async def test_commit_on_clean_exit_in_order(self) -> None:
        session = FakeAsyncSession()
        async with UnitOfWork(session, new_tenant()):  # type: ignore[arg-type]
            pass
        assert session.events == ["begin", "execute", "commit"]

    async def test_rollback_on_exception_and_exception_propagates(self) -> None:
        session = FakeAsyncSession()
        with pytest.raises(ValueError, match="boom"):
            async with UnitOfWork(session, new_tenant()):  # type: ignore[arg-type]
                raise ValueError("boom")
        assert session.events == ["begin", "execute", "rollback"]

    async def test_cancellation_rolls_back(self) -> None:
        import asyncio

        session = FakeAsyncSession()
        with pytest.raises(asyncio.CancelledError):
            async with UnitOfWork(session, new_tenant()):  # type: ignore[arg-type]
                raise asyncio.CancelledError
        assert session.rolled_back and not session.committed

    async def test_failure_to_begin_does_no_further_work(self) -> None:
        session = FakeAsyncSession(fail_on_begin=ConnectionError("db down"))
        with pytest.raises(ConnectionError):
            async with UnitOfWork(session, new_tenant()):  # type: ignore[arg-type]
                pytest.fail("body must not run")
        assert session.events == ["begin"]

    async def test_failure_to_commit_is_not_swallowed(self) -> None:
        session = FakeAsyncSession(fail_on_commit=RuntimeError("commit failed"))
        with pytest.raises(RuntimeError, match="commit failed"):
            async with UnitOfWork(session, new_tenant()):  # type: ignore[arg-type]
                pass

    async def test_can_be_reused_sequentially(self) -> None:
        session = FakeAsyncSession()
        uow = UnitOfWork(session, new_tenant())  # type: ignore[arg-type]
        async with uow:
            pass
        async with uow:
            pass
        assert session.events.count("begin") == 2
        assert session.events.count("commit") == 2

    async def test_explicit_commit_and_rollback_are_noops_outside_a_transaction(self) -> None:
        session = FakeAsyncSession()
        uow = UnitOfWork(session, new_tenant())  # type: ignore[arg-type]
        await uow.commit()
        await uow.rollback()
        assert session.events == []

    async def test_explicit_rollback_inside_transaction(self) -> None:
        session = FakeAsyncSession()
        async with UnitOfWork(session, new_tenant()) as uow:  # type: ignore[arg-type]
            await uow.rollback()
        assert session.rolled_back


class TestAnOpenTransactionIsNeverJoined:
    """A UnitOfWork on a session that already has a transaction would mix tenant contexts and commit work it
    does not own, so it refuses."""

    async def test_it_refuses_a_session_with_an_open_transaction(self) -> None:
        session = FakeAsyncSession()
        session.open_transaction()
        with pytest.raises(TenantIsolationError):
            async with UnitOfWork(session, new_tenant()):  # type: ignore[arg-type]
                pytest.fail("body must not run")

    async def test_a_refused_entry_changes_nothing_on_the_session(self) -> None:
        session = FakeAsyncSession()
        session.open_transaction()
        with pytest.raises(TenantIsolationError):
            async with UnitOfWork(session, new_tenant()):  # type: ignore[arg-type]
                pass
        assert session.events == [], (
            "no begin, no tenant context, and above all no commit or rollback"
        )
        assert session.in_transaction(), "the caller's transaction is untouched"

    async def test_a_second_tenant_cannot_take_over_a_running_unit(self) -> None:
        session = FakeAsyncSession()
        tenant_a, tenant_b = new_tenant(), new_tenant()
        async with UnitOfWork(session, tenant_a):  # type: ignore[arg-type]
            with pytest.raises(TenantIsolationError):
                async with UnitOfWork(session, tenant_b):  # type: ignore[arg-type]
                    pass
            assert session.tenant_setting == str(tenant_a)


class TestTenantContext:
    async def test_tenant_is_set_transaction_locally(self) -> None:
        """`set_config(..., true)` is the SET LOCAL form: it cannot outlive the transaction, so a
        pooled connection can never carry tenant A's id into tenant B's request."""
        session = FakeAsyncSession()
        tenant = new_tenant()
        async with UnitOfWork(session, tenant):  # type: ignore[arg-type]
            pass
        sql, params = session.statements[0]
        assert "set_config('app.tenant_id'" in sql
        assert sql.replace(" ", "").rstrip(")").endswith(",true")
        assert params == {"tid": str(tenant)}

    async def test_tenant_is_set_before_any_caller_statement(self) -> None:
        session = FakeAsyncSession()
        async with UnitOfWork(session, new_tenant()) as uow:  # type: ignore[arg-type]
            await uow.session.execute("SELECT 1")  # type: ignore[arg-type]
        assert "app.tenant_id" in session.statements[0][0]
        assert session.statements[1][0] == "SELECT 1"

    async def test_tenant_value_is_bound_not_interpolated(self) -> None:
        session = FakeAsyncSession()
        tenant = new_tenant()
        async with UnitOfWork(session, tenant):  # type: ignore[arg-type]
            pass
        assert str(tenant) not in session.statements[0][0]

    async def test_system_mode_clears_the_tenant(self) -> None:
        session = FakeAsyncSession()
        async with UnitOfWork(session, None):  # type: ignore[arg-type]
            pass
        assert session.tenant_setting == ""
        assert session.events[:2] == ["begin", "execute"]

    @pytest.mark.parametrize("_", range(3))
    async def test_each_entry_resets_the_tenant(self, _: int) -> None:
        session = FakeAsyncSession()
        tenant = TenantId(uuid4())
        async with UnitOfWork(session, tenant):  # type: ignore[arg-type]
            pass
        assert session.tenant_setting == str(tenant)


class TestTenantUowFactory:
    @staticmethod
    def _factory_returning(session: FakeAsyncSession):  # type: ignore[no-untyped-def]
        @asynccontextmanager
        async def _session_cm() -> AsyncIterator[FakeAsyncSession]:
            yield session

        return lambda: _session_cm()

    async def test_rejects_missing_tenant(self) -> None:
        with pytest.raises(TenantIsolationError):
            async with tenant_uow(None):  # type: ignore[arg-type]
                pytest.fail("must not be entered")

    async def test_does_not_touch_the_database_when_tenant_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom() -> None:
            raise AssertionError("session factory must not be requested")

        monkeypatch.setattr(uow_module, "get_session_factory", _boom)
        with pytest.raises(TenantIsolationError):
            async with tenant_uow(None):  # type: ignore[arg-type]
                pass

    async def test_scopes_the_session_to_the_tenant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = FakeAsyncSession()
        monkeypatch.setattr(
            uow_module, "get_session_factory", lambda: self._factory_returning(session)
        )
        tenant = TenantId(UUID(int=7))
        async with tenant_uow(tenant) as uow:
            assert uow.tenant_id == tenant
        assert session.tenant_setting == str(tenant)
        assert session.committed
