"""Tenant isolation against a real PostgreSQL: the RLS matrix, pool safety and ``UnitOfWork``.

Each RLS test runs in two modes (see ``conftest.rls_mode``): with the policies the architecture
specifies (must pass) and as the repo ships today (DEFECT-09, strict xfail: the day migrations add
real policies those tests start passing and the marker must be removed).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ragassist.shared.db.models import Base
from ragassist.shared.db.uow import UnitOfWork
from ragassist.shared.domain import TenantId

from .conftest import Seed

# (table, column that ties a row to its tenant): discovered from the ORM metadata, not hard-coded.
TENANT_SCOPED = sorted(
    (table.name, "id" if table.name == "tenants" else "tenant_id")
    for table in Base.metadata.sorted_tables
    if table.name == "tenants" or "tenant_id" in table.c
)
COVERED_TABLES = {"tenants", "users"}


async def as_tenant(
    engine: AsyncEngine, tenant: UUID | None, work: Callable[[AsyncSession], object]
) -> object:
    """Run ``work(session)`` inside a real ``UnitOfWork`` for ``tenant``; returns its result."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with UnitOfWork(session, TenantId(tenant) if tenant else None):
            return await work(session)  # type: ignore[misc]


async def rows(engine: AsyncEngine, tenant: UUID | None, sql: str, **params: object) -> list[tuple]:
    async def work(session: AsyncSession) -> list[tuple]:
        result = await session.execute(text(sql), params)
        return [tuple(r) for r in result.all()] if result.returns_rows else []

    return await as_tenant(engine, tenant, work)  # type: ignore[return-value]


async def ground_truth(admin_engine: AsyncEngine, sql: str, **params: object) -> list[tuple]:
    async with admin_engine.connect() as conn:
        return [tuple(r) for r in (await conn.execute(text(sql), params)).all()]


def test_every_tenant_scoped_table_has_matrix_coverage() -> None:
    """A new table with a ``tenant_id`` must be added to this matrix, or this test fails."""
    assert {name for name, _ in TENANT_SCOPED} <= COVERED_TABLES, (
        f"uncovered tenant tables: {TENANT_SCOPED}"
    )


@pytest.mark.parametrize(("table", "column"), TENANT_SCOPED)
class TestRowLevelSecurityMatrix:
    async def test_select_returns_only_the_callers_rows(
        self, rls, seed: Seed, app_engines, table: str, column: str
    ) -> None:
        found = await rows(app_engines(), seed.tenant_a, f"SELECT {column} FROM {table}")
        assert found and {r[0] for r in found} == {seed.tenant_a}

    async def test_aggregates_do_not_leak_other_tenants(
        self, rls, seed: Seed, app_engines, table: str, column: str
    ) -> None:
        (count,) = (await rows(app_engines(), seed.tenant_b, f"SELECT count(*) FROM {table}"))[0]
        expected = len(seed.b_users) if table == "users" else 1
        assert count == expected

    async def test_no_tenant_context_sees_nothing(
        self, rls, seed: Seed, app_engines, table: str, column: str
    ) -> None:
        assert await rows(app_engines(), None, f"SELECT 1 FROM {table}") == []

    async def test_a_garbage_tenant_value_never_exposes_rows(
        self, rls, seed: Seed, app_engines, table: str, column: str
    ) -> None:
        async def work(session: AsyncSession) -> list[tuple]:
            await session.execute(text("SELECT set_config('app.tenant_id', 'not-a-uuid', true)"))
            return [tuple(r) for r in (await session.execute(text(f"SELECT 1 FROM {table}"))).all()]

        try:
            leaked = await as_tenant(app_engines(), seed.tenant_a, work)
        except DBAPIError:
            return  # failing closed is acceptable
        assert leaked == []

    async def test_a_tenant_cannot_move_its_row_to_another_tenant(
        self, rls, seed: Seed, app_engines, table: str, column: str
    ) -> None:
        if table == "tenants":
            pytest.skip("a tenant row has no foreign tenant column")
        with pytest.raises(DBAPIError):
            await rows(
                app_engines(),
                seed.tenant_a,
                f"UPDATE {table} SET {column} = :other WHERE id = :uid",
                other=seed.tenant_b,
                uid=seed.a_users[0],
            )

    async def test_update_of_another_tenants_rows_changes_nothing(
        self, rls, seed: Seed, admin_engine, app_engines, table: str, column: str
    ) -> None:
        target = "name" if table == "tenants" else "role"
        await rows(
            app_engines(),
            seed.tenant_a,
            f"UPDATE {table} SET {target} = 'hacked' WHERE {column} = :b",
            b=seed.tenant_b,
        )
        hacked = await ground_truth(
            admin_engine, f"SELECT count(*) FROM {table} WHERE {target} = 'hacked'"
        )
        assert hacked == [(0,)]

    async def test_delete_of_another_tenants_rows_changes_nothing(
        self, rls, seed: Seed, admin_engine, app_engines, table: str, column: str
    ) -> None:
        if table == "tenants":
            pytest.skip("deleting a tenant cascades; covered by the users case")
        before = await ground_truth(
            admin_engine, f"SELECT count(*) FROM {table} WHERE {column} = :b", b=seed.tenant_b
        )
        await rows(
            app_engines(),
            seed.tenant_a,
            f"DELETE FROM {table} WHERE {column} = :b",
            b=seed.tenant_b,
        )
        assert (
            await ground_truth(
                admin_engine, f"SELECT count(*) FROM {table} WHERE {column} = :b", b=seed.tenant_b
            )
            == before
        )


class TestInsertPolicy:
    async def test_insert_for_the_callers_own_tenant_is_allowed(
        self, spec_rls, seed: Seed, admin_engine, app_engines
    ) -> None:
        uid = uuid4()
        await rows(
            app_engines(),
            seed.tenant_a,
            "INSERT INTO users (id, tenant_id, email, role, created_at) VALUES (:i, :t, 'new@a.example', 'user', now())",
            i=uid,
            t=seed.tenant_a,
        )
        assert await ground_truth(
            admin_engine, "SELECT tenant_id FROM users WHERE id = :i", i=uid
        ) == [(seed.tenant_a,)]

    async def test_insert_into_another_tenant_is_rejected(
        self, rls, seed: Seed, admin_engine, app_engines
    ) -> None:
        uid = uuid4()
        with pytest.raises(DBAPIError):
            await rows(
                app_engines(),
                seed.tenant_a,
                "INSERT INTO users (id, tenant_id, email, role, created_at) VALUES (:i, :t, 'x@b.example', 'user', now())",
                i=uid,
                t=seed.tenant_b,
            )
        assert await ground_truth(admin_engine, "SELECT 1 FROM users WHERE id = :i", i=uid) == []

    async def test_insert_with_no_tenant_context_is_rejected(
        self, rls, seed: Seed, app_engines
    ) -> None:
        with pytest.raises(DBAPIError):
            await rows(
                app_engines(),
                None,
                "INSERT INTO users (id, tenant_id, email, role, created_at) VALUES (:i, :t, 'x@a.example', 'user', now())",
                i=uuid4(),
                t=seed.tenant_a,
            )


class TestPoolSafety:
    """The tenant is set with ``set_config(..., true)``: scoped to the transaction, never the connection."""

    async def test_sequential_tenants_on_one_connection_never_bleed(
        self, rls, seed: Seed, app_engines
    ) -> None:
        engine = app_engines(pool_size=1)
        first = await rows(engine, seed.tenant_a, "SELECT DISTINCT tenant_id FROM users")
        second = await rows(engine, seed.tenant_b, "SELECT DISTINCT tenant_id FROM users")
        assert first == [(seed.tenant_a,)] and second == [(seed.tenant_b,)]

    @pytest.mark.parametrize("mode", ["commit", "exception"])
    async def test_the_tenant_setting_is_cleared_when_the_transaction_ends(
        self, seed: Seed, app_engines, mode: str
    ) -> None:
        engine = app_engines(pool_size=1)
        probe = "SELECT coalesce(current_setting('app.tenant_id', true), '')"
        try:

            async def work(session: AsyncSession) -> None:
                assert (await session.execute(text(probe))).scalar_one() == str(seed.tenant_a)
                if mode == "exception":
                    raise RuntimeError("boom")

            await as_tenant(engine, seed.tenant_a, work)
        except RuntimeError:
            pass
        async with AsyncSession(engine) as plain:  # same pooled connection, no UnitOfWork
            assert (await plain.execute(text(probe))).scalar_one() == ""

    async def test_concurrent_tenants_each_see_only_their_own_rows(
        self, rls, seed: Seed, app_engines
    ) -> None:
        engine = app_engines(pool_size=5)
        tenants = [
            seed.tenant_a,
            seed.tenant_b,
            *seed.extra_tenants,
        ] * 3  # 60 concurrent units of work

        async def one(tenant: UUID) -> set[UUID]:
            found = await rows(engine, tenant, "SELECT DISTINCT tenant_id FROM users")
            await asyncio.sleep(0)
            return {r[0] for r in found}

        results = await asyncio.gather(*[one(t) for t in tenants])
        assert all(seen == {tenant} for seen, tenant in zip(results, tenants, strict=True))


class TestRoleHardening:
    async def test_the_application_role_is_not_privileged(self, pg_server, app_engines) -> None:
        ((superuser, bypass, createrole),) = await rows(
            app_engines(),
            None,
            "SELECT rolsuper, rolbypassrls, rolcreaterole FROM pg_roles WHERE rolname = current_user",
        )
        assert (superuser, bypass, createrole) == (False, False, False)

    async def test_the_application_role_does_not_own_the_tenant_tables(
        self, seed: Seed, app_engines
    ) -> None:
        owners = await rows(
            app_engines(),
            None,
            "SELECT DISTINCT tableowner FROM pg_tables WHERE tablename IN ('users','tenants')",
        )
        assert owners and all(owner != "app_user" for (owner,) in owners)

    async def test_every_tenant_table_has_forced_row_level_security(
        self, seed: Seed, admin_engine
    ) -> None:
        flags = await ground_truth(
            admin_engine,
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(:names)",
            names=[name for name, _ in TENANT_SCOPED],
        )
        assert flags and all(enabled and forced for _, enabled, forced in flags)

    async def test_every_tenant_table_has_a_policy(self, seed: Seed, admin_engine) -> None:
        policies = {
            t for (t,) in await ground_truth(admin_engine, "SELECT tablename FROM pg_policies")
        }
        assert {name for name, _ in TENANT_SCOPED} <= policies


class TestUnitOfWorkOnARealSession:
    async def test_commit_persists_and_rollback_discards(
        self, seed: Seed, admin_engine, app_engines
    ) -> None:
        engine = app_engines()
        keep, drop = uuid4(), uuid4()
        insert = "INSERT INTO users (id, tenant_id, email, role, created_at) VALUES (:i, :t, 'x@a.example', 'user', now())"
        await rows(engine, seed.tenant_a, insert, i=keep, t=seed.tenant_a)
        with pytest.raises(RuntimeError):

            async def work(session: AsyncSession) -> None:
                await session.execute(text(insert), {"i": drop, "t": seed.tenant_a})
                raise RuntimeError("boom")

            await as_tenant(engine, seed.tenant_a, work)
        present = {
            r[0]
            for r in await ground_truth(
                admin_engine, "SELECT id FROM users WHERE id = ANY(:ids)", ids=[keep, drop]
            )
        }
        assert present == {keep}

    async def test_the_tenant_is_visible_inside_the_transaction(
        self, seed: Seed, app_engines
    ) -> None:
        (value,) = (
            await rows(app_engines(), seed.tenant_b, "SELECT current_setting('app.tenant_id')")
        )[0]
        assert value == str(seed.tenant_b)

    async def test_no_tenant_sets_an_empty_context(self, seed: Seed, app_engines) -> None:
        (value,) = (await rows(app_engines(), None, "SELECT current_setting('app.tenant_id')"))[0]
        assert value == ""

    async def test_the_original_exception_propagates_unchanged(
        self, seed: Seed, app_engines
    ) -> None:
        class Marker(Exception):
            pass

        async def work(session: AsyncSession) -> None:
            raise Marker("original")

        with pytest.raises(Marker, match="original"):
            await as_tenant(app_engines(), seed.tenant_a, work)

    async def test_a_failed_statement_rolls_back_and_the_pool_recovers(
        self, seed: Seed, app_engines
    ) -> None:
        engine = app_engines(pool_size=1)
        with pytest.raises(DBAPIError):
            await rows(engine, seed.tenant_a, "SELECT * FROM table_that_does_not_exist")
        assert await rows(engine, seed.tenant_a, "SELECT 1") == [(1,)]

    async def test_works_on_a_session_that_has_already_started_a_transaction(
        self, seed: Seed, app_engines
    ) -> None:
        """A session that ran a query (autobegin) must still be usable with the UnitOfWork, e.g. when a
        FastAPI dependency touched the shared session first."""
        async with AsyncSession(app_engines()) as session:
            await session.execute(text("SELECT 1"))
            try:
                async with UnitOfWork(session, TenantId(seed.tenant_a)):
                    pass
            except InvalidRequestError as exc:
                pytest.fail(f"UnitOfWork cannot join an already-begun transaction: {exc}")

    async def test_tenant_uow_uses_the_configured_database(
        self, seed: Seed, pg_server, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ragassist.shared.config import settings as settings_module
        from ragassist.shared.db import session as session_module
        from ragassist.shared.db.uow import tenant_uow

        monkeypatch.setenv("DATABASE_URL", pg_server.app_url)
        settings_module._settings = None
        session_module._engine = None
        session_module._session_factory = None
        try:
            async with tenant_uow(TenantId(seed.tenant_a)) as uow:
                value = (
                    await uow.session.execute(text("SELECT current_setting('app.tenant_id')"))
                ).scalar_one()
            assert value == str(seed.tenant_a)
        finally:
            if session_module._engine is not None:
                await session_module._engine.dispose()
            session_module._engine = None
            session_module._session_factory = None
