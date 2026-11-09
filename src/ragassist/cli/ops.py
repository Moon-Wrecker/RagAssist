"""Operator commands: ``db upgrade``, ``seed`` and ``token``.

Every connection detail and secret comes from the settings (``.env``); nothing is configured here.

Sources consulted (AGENTS.md section 3.5):
- Alembic, "Using Asyncio with Alembic" and the programmatic API (``alembic.command.upgrade``).
- LangGraph ``AsyncPostgresSaver.setup()`` (creates the checkpoint tables; needs an owner role).
- psycopg 3 on Windows: the async API needs a selector event loop, hence ``run_async`` below.
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections.abc import Coroutine
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import typer

from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.security.jwt import UserRole, create_access_token

db_app = typer.Typer(help="Database operations", no_args_is_help=True)
workspace_app = typer.Typer(help="Workspace (tenant) administration", no_args_is_help=True)

#: Demo tenants. The ids match the mock SaaS accounts, so account tools resolve for them.
DEMO_TENANTS: dict[str, tuple[UUID, str]] = {
    "acme": (UUID("a0000000-0000-0000-0000-000000000001"), "Acme Corp"),
    "globex": (UUID("b0000000-0000-0000-0000-000000000002"), "Globex Inc"),
}
_NAMESPACE = UUID("6f1f8e3a-0c53-4a41-9a52-3d6f7f1c0a11")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on a loop psycopg supports (the selector loop on Windows)."""
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(coro)


def demo_user_id(tenant: str, role: UserRole) -> UUID:
    """Stable id for a demo user, so tokens minted by ``token`` match the rows ``seed`` wrote."""
    return uuid5(_NAMESPACE, f"{tenant}:{role.value}")


def resolve_tenant(value: str) -> UUID:
    if value.lower() in DEMO_TENANTS:
        return DEMO_TENANTS[value.lower()][0]
    try:
        return UUID(value)
    except ValueError as exc:
        raise typer.BadParameter(f"use a tenant UUID or one of: {', '.join(DEMO_TENANTS)}") from exc


# --------------------------------------------------------------------------------------------------
# db upgrade
# --------------------------------------------------------------------------------------------------


def _alembic_upgrade(root: Path) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")


async def _setup_checkpointer_and_grants(settings: Settings) -> None:
    """Create the LangGraph checkpoint tables as the owner, then let the application role use them."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg import sql

    from ragassist.runtime import psycopg_conninfo

    if not _IDENTIFIER.match(settings.DB_APP_USER):
        raise typer.BadParameter("DB_APP_USER is not a plain identifier")
    app_role = sql.Identifier(settings.DB_APP_USER)
    async with AsyncPostgresSaver.from_conn_string(psycopg_conninfo(settings.DATABASE_ADMIN_URL)) as saver:
        await saver.setup()
        async with saver.conn.cursor() as cur:
            await cur.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(app_role))
            await cur.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(app_role))


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply the schema migrations and create the LangGraph checkpoint tables."""
    settings = get_settings()
    root = Path.cwd()
    _alembic_upgrade(root)
    run_async(_setup_checkpointer_and_grants(settings))
    typer.echo("Database is up to date.")


# --------------------------------------------------------------------------------------------------
# seed
# --------------------------------------------------------------------------------------------------


async def _seed(settings: Settings) -> list[str]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.DATABASE_ADMIN_URL)
    lines: list[str] = []
    try:
        async with engine.begin() as conn:
            for slug, (tenant_id, name) in DEMO_TENANTS.items():
                await conn.execute(
                    text("INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :slug) ON CONFLICT (id) DO NOTHING"),
                    {"id": tenant_id, "name": name, "slug": slug},
                )
                for role in (UserRole.ADMIN, UserRole.AGENT, UserRole.USER):
                    await conn.execute(
                        text(
                            "INSERT INTO users (id, tenant_id, email, role) VALUES (:id, :tid, :email, :role) "
                            "ON CONFLICT (id) DO NOTHING"
                        ),
                        {
                            "id": demo_user_id(slug, role),
                            "tid": tenant_id,
                            "email": f"{role.value}@{slug}.example.com",
                            "role": role.value,
                        },
                    )
                lines.append(f"{slug}: tenant {tenant_id} with admin, agent and user")
    finally:
        await engine.dispose()
    return lines


async def _identity_services(settings: Settings):  # type: ignore[no-untyped-def]
    """Identity services on the application role's connection (row-level security applies, as in the API)."""
    from ragassist.modules.identity.adapters.postgres import PostgresIdentityStore
    from ragassist.modules.identity.wiring import build_identity
    from ragassist.shared.db.scoped import ScopedDatabase
    from ragassist.shared.db.session import get_engine, get_session_factory

    engine = get_engine(settings)
    services = build_identity(settings, PostgresIdentityStore(ScopedDatabase(get_session_factory(settings))))
    return services, engine


async def _demo_links(settings: Settings) -> list[str]:
    """One set-password link for each demo account (they are created without a password)."""
    services, engine = await _identity_services(settings)
    lines: list[str] = []
    try:
        for slug, (tenant_id, _) in DEMO_TENANTS.items():
            for role in (UserRole.ADMIN, UserRole.AGENT, UserRole.USER):
                link = await services.accounts.setup_link_for(tenant_id, demo_user_id(slug, role))
                lines.append(f"  {slug:<7} {link.email:<28} {link.url}")
    finally:
        await engine.dispose()
    return lines


def seed_command() -> None:
    """Create the demo tenants (Acme, Globex) with an admin, an agent and a user each."""
    settings = get_settings()
    for line in run_async(_seed(settings)):
        typer.echo(line)
    typer.echo("\nSet each account's password with its one-time link (valid for AUTH_INVITE_HOURS hours):")
    for line in run_async(_demo_links(settings)):
        typer.echo(line)
    typer.echo("\nFor API testing without a password: ragassist token --tenant acme --role admin")


async def _create_workspace(settings: Settings, name: str, slug: str, admin_email: str) -> tuple[str, str, str]:
    services, engine = await _identity_services(settings)
    try:
        workspace, link = await services.accounts.create_workspace(name, slug, admin_email)
    finally:
        await engine.dispose()
    return str(workspace.id), workspace.slug, link.url


@workspace_app.command("create")
def workspace_create(
    name: str = typer.Option(..., "--name", help="Display name of the workspace"),
    slug: str = typer.Option(..., "--slug", help="What people type at sign-in (lower-case, digits, hyphens)"),
    admin_email: str = typer.Option(..., "--admin-email", help="Email of the first administrator"),
) -> None:
    """Create a workspace and print the one-time link its first administrator uses to set a password."""
    from ragassist.shared.domain import DomainError

    try:
        workspace_id, final_slug, url = run_async(_create_workspace(get_settings(), name, slug, admin_email))
    except DomainError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Workspace '{final_slug}' created ({workspace_id}).")
    typer.echo("Give the administrator this link; it is shown once and works once:")
    typer.echo(url)


def token_command(
    tenant: str = typer.Option("acme", "--tenant", "-t", help="Tenant UUID, or: acme, globex"),
    role: UserRole = typer.Option(UserRole.USER, "--role", "-r", help="user, agent or admin"),
    user_id: str = typer.Option("", "--user-id", help="User UUID (default: the seeded demo user)"),
    minutes: int = typer.Option(0, "--minutes", help="Lifetime in minutes (default: JWT_ACCESS_TOKEN_EXPIRE_MINUTES)"),
) -> None:
    """Print a signed access token for local testing (use it as `Authorization: Bearer <token>`)."""
    tenant_id = resolve_tenant(tenant)
    slug = next((s for s, (tid, _) in DEMO_TENANTS.items() if tid == tenant_id), str(tenant_id))
    uid = UUID(user_id) if user_id else demo_user_id(slug, role)
    token = create_access_token(
        user_id=uid,  # type: ignore[arg-type]
        tenant_id=tenant_id,  # type: ignore[arg-type]
        role=role,
        expires_delta=timedelta(minutes=minutes) if minutes else None,
    )
    typer.echo(token)
