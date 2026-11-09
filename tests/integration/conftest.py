"""Integration tier: real PostgreSQL (pgvector image) started with testcontainers.

* Postgres comes from one of two places, so the tier runs both on a laptop and in CI:
    - ``TEST_DATABASE_ADMIN_URL`` (e.g. a GitHub Actions ``services: postgres`` container), or
    - a throwaway pgvector container started with testcontainers (needs Docker).
  An external database is wiped by the tests, so its name must contain "test"
  (or set ``RAGASSIST_TEST_DB_ALLOW_WIPE=1``): the dev database can never be hit by accident.
* Either way it is bootstrapped exactly like production: the project's own
  ``infra/postgres/init.sql`` (extensions + the non-superuser ``app_user``), then the schema.
* Schema comes from Alembic once migrations exist; until then from the SQLAlchemy metadata.
* Every test gets a clean, seeded database; engines are created per test (asyncpg connections are
  bound to the event loop that opened them).
* The whole tier skips with a reason when Docker is unavailable.

``rls_mode`` runs a test twice: ``spec_policies`` applies the RLS policies the architecture
specifies (they must pass: this proves both the tests and ``UnitOfWork``), ``as_shipped`` uses the
schema exactly as the repo creates it today (DEFECT-09: no policies yet, so isolation tests xfail).
"""

from __future__ import annotations

import asyncio
import os
import secrets
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from urllib.parse import quote
from uuid import UUID, uuid4

os.environ.setdefault(
    "TESTCONTAINERS_RYUK_DISABLED", "true"
)  # the reaper image is unreliable on Windows

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from support.repo import REPO_ROOT

from ragassist.shared.db.models import Base

PG_IMAGE = "pgvector/pgvector:pg16"
DB_NAME = "ragassist"
CURRENT_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

SPEC_POLICIES = f"""
DROP POLICY IF EXISTS tenant_isolation ON users;
DROP POLICY IF EXISTS tenant_isolation ON tenants;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON users
    USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT});
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenants
    USING (id = {CURRENT_TENANT}) WITH CHECK (id = {CURRENT_TENANT});
"""
DROP_POLICIES = """
DROP POLICY IF EXISTS tenant_isolation ON users;
DROP POLICY IF EXISTS tenant_isolation ON tenants;
"""


def _docker_ok() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@dataclass(frozen=True)
class PgServer:
    """A throwaway Postgres. Every credential is generated at run time; none is committed."""

    host: str
    port: int
    admin_user: str
    admin_password: str
    database: str = DB_NAME
    app_user: str = "app_user"  # a role name, not a secret
    app_role_secret: str = field(default_factory=lambda: secrets.token_urlsafe(24))

    def url(self, user: str, password: str) -> str:
        return (
            f"postgresql+asyncpg://{quote(user, safe='')}:{quote(password, safe='')}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def admin_url(self) -> str:
        return self.url(self.admin_user, self.admin_password)

    @property
    def app_url(self) -> str:
        return self.url(self.app_user, self.app_role_secret)


def _register_models() -> None:
    """Import every ORM model module so Base.metadata knows every table before create_all."""
    import importlib

    for module in ("ragassist.modules.knowledge.adapters.persistence.models",):
        try:
            importlib.import_module(module)
        except ImportError:  # a module that is not written yet contributes no tables
            pass


async def _bootstrap(server: PgServer) -> None:
    engine = create_async_engine(server.admin_url, poolclass=NullPool)
    try:
        init_sql = (REPO_ROOT / "infra" / "postgres" / "init.sql").read_text(encoding="utf-8")
        # The same bootstrap as infra/postgres/create-app-role.sh: a restricted role with a generated password.
        role_sql = (
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{server.app_user}') THEN "
            f"CREATE ROLE {server.app_user} LOGIN PASSWORD '{server.app_role_secret}' NOSUPERUSER NOBYPASSRLS; "
            f"ELSE ALTER ROLE {server.app_user} PASSWORD '{server.app_role_secret}'; END IF; END $$;"
            f' GRANT ALL PRIVILEGES ON DATABASE "{server.database}" TO {server.app_user};'
            f" GRANT ALL ON SCHEMA public TO {server.app_user};"
            f" ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {server.app_user};"
            f" ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {server.app_user};"
        )
        async with engine.connect() as conn:
            raw = await conn.get_raw_connection()
            await raw.driver_connection.execute(f"{init_sql}\n{role_sql}")  # simple-query protocol
            await conn.commit()
        if (REPO_ROOT / "alembic.ini").exists() and list(
            (REPO_ROOT / "migrations").rglob("versions/*.py")
        ):
            env = {
                **os.environ,
                "DATABASE_ADMIN_URL": server.admin_url,
                "DATABASE_URL": server.app_url,
            }
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=REPO_ROOT,
                env=env,
                check=True,
            )
        else:
            _register_models()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def _external_server() -> PgServer | None:
    """The Postgres named by ``TEST_DATABASE_ADMIN_URL``, or None when it is not set."""
    raw = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not raw:
        return None
    url = make_url(raw)
    database = url.database or DB_NAME
    if "test" not in database.lower() and os.environ.get("RAGASSIST_TEST_DB_ALLOW_WIPE") != "1":
        pytest.skip(
            f"TEST_DATABASE_ADMIN_URL points at {database!r}, which the tests would wipe. Use a database whose "
            "name contains 'test' or set RAGASSIST_TEST_DB_ALLOW_WIPE=1."
        )
    return PgServer(
        host=url.host or "localhost",
        port=url.port or 5432,
        database=database,
        admin_user=url.username or "",
        admin_password=url.password or "",
    )


@pytest.fixture(scope="session")
def pg_server() -> Iterator[PgServer]:
    external = _external_server()
    if external is not None:
        asyncio.run(_bootstrap(external))
        yield external
        return
    if not _docker_ok():
        pytest.skip(
            "No TEST_DATABASE_ADMIN_URL and Docker is unavailable: integration tier skipped"
        )
    from testcontainers.postgres import PostgresContainer

    admin_user, admin_password = "test_admin", secrets.token_urlsafe(24)
    container = PostgresContainer(
        PG_IMAGE, username=admin_user, password=admin_password, dbname=DB_NAME, driver="asyncpg"
    )
    container.start()
    try:
        server = PgServer(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(5432)),
            admin_user=admin_user,
            admin_password=admin_password,
        )
        asyncio.run(_bootstrap(server))
        yield server
    finally:
        container.stop()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Containers and image pulls are slow: give the whole tier a generous per-test timeout."""
    for item in items:
        if "tests/integration" in item.nodeid.replace("\\", "/") and not item.get_closest_marker(
            "timeout"
        ):
            item.add_marker(pytest.mark.timeout(240))


@pytest.fixture
async def admin_engine(pg_server: PgServer) -> AsyncIterator[AsyncEngine]:
    """Superuser engine: bypasses RLS, used only to seed and to verify ground truth."""
    engine = create_async_engine(pg_server.admin_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_engines(pg_server: PgServer) -> AsyncIterator[Callable[..., AsyncEngine]]:
    """Engines connecting as the non-superuser ``app_user`` (what the API uses in production)."""
    created: list[AsyncEngine] = []

    def build(*, pool_size: int = 5, max_overflow: int = 0) -> AsyncEngine:
        engine = create_async_engine(
            pg_server.app_url, pool_size=pool_size, max_overflow=max_overflow
        )
        created.append(engine)
        return engine

    yield build
    for engine in created:
        await engine.dispose()


async def run_script(engine: AsyncEngine, sql: str) -> None:
    """Run a multi-statement SQL script (asyncpg only allows that on the simple-query protocol)."""
    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        await raw.driver_connection.execute(sql)
        await conn.commit()


@dataclass
class Seed:
    tenant_a: UUID
    tenant_b: UUID
    users: dict[UUID, list[UUID]] = field(default_factory=dict)  # tenant id -> user ids
    extra_tenants: list[UUID] = field(default_factory=list)

    @property
    def a_users(self) -> list[UUID]:
        return self.users[self.tenant_a]

    @property
    def b_users(self) -> list[UUID]:
        return self.users[self.tenant_b]


@pytest.fixture(
    params=[
        "spec_policies",
        "as_shipped",
    ]
)
def rls_mode(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
async def clean_db(admin_engine: AsyncEngine) -> AsyncIterator[None]:
    await run_script(
        admin_engine, DROP_POLICIES + "TRUNCATE users, tenants RESTART IDENTITY CASCADE;"
    )
    yield
    await run_script(
        admin_engine, DROP_POLICIES + "TRUNCATE users, tenants RESTART IDENTITY CASCADE;"
    )


@pytest.fixture
async def seed(admin_engine: AsyncEngine, clean_db: None) -> Seed:
    """Tenant A and B with two users each, plus 18 more single-user tenants for concurrency tests."""
    data = Seed(tenant_a=uuid4(), tenant_b=uuid4())
    tenants = [(data.tenant_a, "Acme", "acme"), (data.tenant_b, "Globex", "globex")]
    for i in range(18):
        tenant = uuid4()
        data.extra_tenants.append(tenant)
        tenants.append((tenant, f"Tenant {i}", f"tenant-{i}"))
    async with admin_engine.begin() as conn:
        for tenant_id, name, slug in tenants:
            await conn.execute(
                text("INSERT INTO tenants (id, name, slug, created_at) VALUES (:i, :n, :s, now())"),
                {"i": tenant_id, "n": name, "s": slug},
            )
            count = 2 if tenant_id in (data.tenant_a, data.tenant_b) else 1
            data.users[tenant_id] = []
            for n in range(count):
                user_id = uuid4()
                data.users[tenant_id].append(user_id)
                await conn.execute(
                    text(
                        "INSERT INTO users (id, tenant_id, email, role, created_at) VALUES (:i, :t, :e, 'user', now())"
                    ),
                    {"i": user_id, "t": tenant_id, "e": f"u{n}@{tenant_id.hex[:6]}.example"},
                )
    return data


@pytest.fixture
async def rls(rls_mode: str, seed: Seed, admin_engine: AsyncEngine) -> str:
    """Seeded database with the policies of the chosen mode applied."""
    if rls_mode == "spec_policies":
        await run_script(admin_engine, SPEC_POLICIES)
    return rls_mode


@pytest.fixture
async def spec_rls(seed: Seed, admin_engine: AsyncEngine) -> str:
    """Seeded database with the specified policies, for behaviour that holds in that mode only."""
    await run_script(admin_engine, SPEC_POLICIES)
    return "spec_policies"
