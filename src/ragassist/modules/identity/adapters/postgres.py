"""PostgreSQL identity store (row-level-security scoped).

Goal: persist workspaces, accounts, refresh sessions and invite links so that PostgreSQL itself keeps every
tenant's rows apart (AGENTS.md section 1.3). Every query runs inside ``ScopedDatabase.scope(tenant_id)`` and also
names ``tenant_id`` in its ``WHERE``, so an application bug alone cannot cross a tenant boundary.

The one lookup that has no tenant yet is "which workspace does this slug name?". It sets the transaction-local
``app.tenant_slug``, which the ``tenants_slug_lookup`` policy (migration 0002) reads, and returns that single row
and nothing else.

Single-use claims (``claim_session``, ``claim_invite``) are one ``UPDATE ... WHERE <unused> RETURNING`` each, so two
concurrent requests cannot both win.

Consulted: PostgreSQL row security policies and ``set_config(..., is_local => true)``, SQLAlchemy 2.0 asyncio
``text()`` with bound parameters, asyncpg unique-violation behaviour (``IntegrityError``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ragassist.modules.identity.domain import (
    AccountConflictError,
    InviteKind,
    InviteRecord,
    SessionRecord,
    UserRecord,
    UserStatus,
    Workspace,
    WorkspaceExistsError,
)
from ragassist.shared.db.scoped import ScopedDatabase
from ragassist.shared.security.jwt import UserRole

_USER_COLUMNS = "id, tenant_id, email, role, status, password_hash"
_INVITE_COLUMNS = (
    "id, tenant_id, kind, email, role, user_id, token_hash, created_by, expires_at, accepted_at, revoked_at, created_at"
)
_SESSION_COLUMNS = "id, tenant_id, user_id, family_id, token_hash, expires_at, rotated_at, revoked_at"


def _user(row: Any) -> UserRecord:
    return UserRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        email=row.email,
        role=UserRole(row.role),
        status=UserStatus(row.status),
        password_hash=row.password_hash,
    )


def _session(row: Any) -> SessionRecord:
    return SessionRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        family_id=row.family_id,
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        rotated_at=row.rotated_at,
        revoked_at=row.revoked_at,
    )


def _invite(row: Any) -> InviteRecord:
    return InviteRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        kind=InviteKind(row.kind),
        email=row.email,
        role=UserRole(row.role),
        user_id=row.user_id,
        token_hash=row.token_hash,
        created_by=row.created_by,
        expires_at=row.expires_at,
        accepted_at=row.accepted_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


def _is_unique_violation(exc: IntegrityError, constraint_hint: str) -> bool:
    return constraint_hint in str(exc.orig)


class PostgresIdentityStore:
    def __init__(self, database: ScopedDatabase) -> None:
        self._db = database

    # --- workspaces ---------------------------------------------------------------------------
    async def workspace_by_slug(self, slug: str) -> Workspace | None:
        async with self._db.scope(None) as session:
            await session.execute(text("SELECT set_config('app.tenant_slug', :slug, true)"), {"slug": slug})
            row = (
                await session.execute(
                    text("SELECT id, name, slug FROM tenants WHERE slug = :slug"), {"slug": slug}
                )
            ).first()
        return Workspace(id=row.id, name=row.name, slug=row.slug) if row else None

    async def workspace_by_id(self, tenant_id: UUID) -> Workspace | None:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text("SELECT id, name, slug FROM tenants WHERE id = :tid"), {"tid": tenant_id}
                )
            ).first()
        return Workspace(id=row.id, name=row.name, slug=row.slug) if row else None

    async def create_workspace(self, workspace: Workspace, admin: UserRecord) -> None:
        try:
            async with self._db.scope(workspace.id) as session:
                await session.execute(
                    text("INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :slug)"),
                    {"id": workspace.id, "name": workspace.name, "slug": workspace.slug},
                )
                await session.execute(
                    text(
                        "INSERT INTO users (id, tenant_id, email, role, status) "
                        "VALUES (:id, :tid, :email, :role, :status)"
                    ),
                    {
                        "id": admin.id,
                        "tid": workspace.id,
                        "email": admin.email,
                        "role": admin.role.value,
                        "status": admin.status.value,
                    },
                )
        except IntegrityError as exc:
            if _is_unique_violation(exc, "slug"):
                raise WorkspaceExistsError("A workspace with that slug already exists.") from exc
            raise

    # --- users --------------------------------------------------------------------------------
    async def user_by_email(self, tenant_id: UUID, email: str) -> UserRecord | None:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(f"SELECT {_USER_COLUMNS} FROM users WHERE tenant_id = :tid AND lower(email) = :email"),
                    {"tid": tenant_id, "email": email.lower()},
                )
            ).first()
        return _user(row) if row else None

    async def user_by_id(self, tenant_id: UUID, user_id: UUID) -> UserRecord | None:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(f"SELECT {_USER_COLUMNS} FROM users WHERE tenant_id = :tid AND id = :id"),
                    {"tid": tenant_id, "id": user_id},
                )
            ).first()
        return _user(row) if row else None

    async def list_users(self, tenant_id: UUID) -> list[UserRecord]:
        async with self._db.scope(tenant_id) as session:
            rows = (
                await session.execute(
                    text(f"SELECT {_USER_COLUMNS} FROM users WHERE tenant_id = :tid ORDER BY lower(email)"),
                    {"tid": tenant_id},
                )
            ).all()
        return [_user(r) for r in rows]

    async def add_user(self, user: UserRecord) -> None:
        try:
            async with self._db.scope(user.tenant_id) as session:
                await session.execute(
                    text(
                        "INSERT INTO users (id, tenant_id, email, role, status, password_hash) "
                        "VALUES (:id, :tid, :email, :role, :status, :hash)"
                    ),
                    {
                        "id": user.id,
                        "tid": user.tenant_id,
                        "email": user.email,
                        "role": user.role.value,
                        "status": user.status.value,
                        "hash": user.password_hash,
                    },
                )
        except IntegrityError as exc:
            if _is_unique_violation(exc, "uq_users_tenant_email"):
                raise AccountConflictError("That address already has an account in this workspace.") from exc
            raise

    async def set_password_hash(self, tenant_id: UUID, user_id: UUID, password_hash: str) -> None:
        async with self._db.scope(tenant_id) as session:
            await session.execute(
                text("UPDATE users SET password_hash = :hash WHERE tenant_id = :tid AND id = :id"),
                {"hash": password_hash, "tid": tenant_id, "id": user_id},
            )

    async def update_user(
        self, tenant_id: UUID, user_id: UUID, *, role: str | None = None, status: str | None = None
    ) -> UserRecord | None:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(
                        "UPDATE users SET role = COALESCE(:role, role), status = COALESCE(:status, status) "
                        f"WHERE tenant_id = :tid AND id = :id RETURNING {_USER_COLUMNS}"
                    ),
                    {"role": role, "status": status, "tid": tenant_id, "id": user_id},
                )
            ).first()
        return _user(row) if row else None

    async def count_active_admins(self, tenant_id: UUID) -> int:
        async with self._db.scope(tenant_id) as session:
            return int(
                (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM users "
                            "WHERE tenant_id = :tid AND role = 'admin' AND status = 'active'"
                        ),
                        {"tid": tenant_id},
                    )
                ).scalar_one()
            )

    # --- sessions -----------------------------------------------------------------------------
    async def add_session(self, session_record: SessionRecord) -> None:
        async with self._db.scope(session_record.tenant_id) as session:
            await session.execute(
                text(
                    "INSERT INTO auth_sessions (id, tenant_id, user_id, family_id, token_hash, expires_at) "
                    "VALUES (:id, :tid, :uid, :family, :hash, :expires)"
                ),
                {
                    "id": session_record.id,
                    "tid": session_record.tenant_id,
                    "uid": session_record.user_id,
                    "family": session_record.family_id,
                    "hash": session_record.token_hash,
                    "expires": session_record.expires_at,
                },
            )

    async def get_session(self, tenant_id: UUID, token_hash: str) -> SessionRecord | None:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(
                        f"SELECT {_SESSION_COLUMNS} FROM auth_sessions "
                        "WHERE tenant_id = :tid AND token_hash = :hash"
                    ),
                    {"tid": tenant_id, "hash": token_hash},
                )
            ).first()
        return _session(row) if row else None

    async def claim_session(self, tenant_id: UUID, session_id: UUID, now: datetime) -> bool:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(
                        "UPDATE auth_sessions SET rotated_at = :now WHERE tenant_id = :tid AND id = :id "
                        "AND rotated_at IS NULL AND revoked_at IS NULL RETURNING id"
                    ),
                    {"now": now, "tid": tenant_id, "id": session_id},
                )
            ).first()
        return row is not None

    async def revoke_family(self, tenant_id: UUID, family_id: UUID, now: datetime) -> None:
        async with self._db.scope(tenant_id) as session:
            await session.execute(
                text(
                    "UPDATE auth_sessions SET revoked_at = :now "
                    "WHERE tenant_id = :tid AND family_id = :family AND revoked_at IS NULL"
                ),
                {"now": now, "tid": tenant_id, "family": family_id},
            )

    async def revoke_user_sessions(self, tenant_id: UUID, user_id: UUID, now: datetime) -> None:
        async with self._db.scope(tenant_id) as session:
            await session.execute(
                text(
                    "UPDATE auth_sessions SET revoked_at = :now "
                    "WHERE tenant_id = :tid AND user_id = :uid AND revoked_at IS NULL"
                ),
                {"now": now, "tid": tenant_id, "uid": user_id},
            )

    # --- invites ------------------------------------------------------------------------------
    async def add_invite(self, invite: InviteRecord) -> None:
        try:
            async with self._db.scope(invite.tenant_id) as session:
                await session.execute(
                    text(
                        "INSERT INTO invites (id, tenant_id, kind, email, role, user_id, token_hash, "
                        "created_by, expires_at) VALUES (:id, :tid, :kind, :email, :role, :uid, :hash, "
                        ":created_by, :expires)"
                    ),
                    {
                        "id": invite.id,
                        "tid": invite.tenant_id,
                        "kind": invite.kind.value,
                        "email": invite.email,
                        "role": invite.role.value,
                        "uid": invite.user_id,
                        "hash": invite.token_hash,
                        "created_by": invite.created_by,
                        "expires": invite.expires_at,
                    },
                )
        except IntegrityError as exc:
            if _is_unique_violation(exc, "uq_invites_pending_email"):
                raise AccountConflictError("That address already has a pending invite.") from exc
            raise

    async def get_invite(self, tenant_id: UUID, token_hash: str) -> InviteRecord | None:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(f"SELECT {_INVITE_COLUMNS} FROM invites WHERE tenant_id = :tid AND token_hash = :hash"),
                    {"tid": tenant_id, "hash": token_hash},
                )
            ).first()
        return _invite(row) if row else None

    async def get_invite_by_id(self, tenant_id: UUID, invite_id: UUID) -> InviteRecord | None:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(f"SELECT {_INVITE_COLUMNS} FROM invites WHERE tenant_id = :tid AND id = :id"),
                    {"tid": tenant_id, "id": invite_id},
                )
            ).first()
        return _invite(row) if row else None

    async def list_pending_invites(self, tenant_id: UUID, now: datetime) -> list[InviteRecord]:
        async with self._db.scope(tenant_id) as session:
            rows = (
                await session.execute(
                    text(
                        f"SELECT {_INVITE_COLUMNS} FROM invites WHERE tenant_id = :tid "
                        "AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > :now "
                        "ORDER BY created_at DESC"
                    ),
                    {"tid": tenant_id, "now": now},
                )
            ).all()
        return [_invite(r) for r in rows]

    async def claim_invite(self, tenant_id: UUID, invite_id: UUID, now: datetime) -> bool:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(
                        "UPDATE invites SET accepted_at = :now WHERE tenant_id = :tid AND id = :id "
                        "AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > :now RETURNING id"
                    ),
                    {"now": now, "tid": tenant_id, "id": invite_id},
                )
            ).first()
        return row is not None

    async def revoke_invite(self, tenant_id: UUID, invite_id: UUID, now: datetime) -> bool:
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text(
                        "UPDATE invites SET revoked_at = :now WHERE tenant_id = :tid AND id = :id "
                        "AND accepted_at IS NULL AND revoked_at IS NULL RETURNING id"
                    ),
                    {"now": now, "tid": tenant_id, "id": invite_id},
                )
            ).first()
        return row is not None

    async def revoke_invites_for_user(self, tenant_id: UUID, user_id: UUID, now: datetime) -> None:
        async with self._db.scope(tenant_id) as session:
            await session.execute(
                text(
                    "UPDATE invites SET revoked_at = :now WHERE tenant_id = :tid AND user_id = :uid "
                    "AND accepted_at IS NULL AND revoked_at IS NULL"
                ),
                {"now": now, "tid": tenant_id, "uid": user_id},
            )
