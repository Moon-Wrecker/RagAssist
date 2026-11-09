"""In-process identity store for the automated tests and the ``memory`` persistence backend.

It mirrors ``PostgresIdentityStore`` rule for rule (tenant scoping, uniqueness, single-use claims) so a use case
behaves the same on either, and so the unit tests exercise the real logic without a database.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

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
from ragassist.shared.security.jwt import UserRole


class InMemoryIdentityStore:
    def __init__(self) -> None:
        self._workspaces: dict[UUID, Workspace] = {}
        self._users: dict[UUID, UserRecord] = {}
        self._sessions: dict[UUID, SessionRecord] = {}
        self._invites: dict[UUID, InviteRecord] = {}

    # --- workspaces ---------------------------------------------------------------------------
    async def workspace_by_slug(self, slug: str) -> Workspace | None:
        return next((w for w in self._workspaces.values() if w.slug == slug), None)

    async def workspace_by_id(self, tenant_id: UUID) -> Workspace | None:
        return self._workspaces.get(tenant_id)

    async def create_workspace(self, workspace: Workspace, admin: UserRecord) -> None:
        if await self.workspace_by_slug(workspace.slug) is not None:
            raise WorkspaceExistsError("A workspace with that slug already exists.")
        self._workspaces[workspace.id] = workspace
        self._users[admin.id] = admin

    # --- users --------------------------------------------------------------------------------
    async def user_by_email(self, tenant_id: UUID, email: str) -> UserRecord | None:
        return next(
            (u for u in self._users.values() if u.tenant_id == tenant_id and u.email.lower() == email.lower()),
            None,
        )

    async def user_by_id(self, tenant_id: UUID, user_id: UUID) -> UserRecord | None:
        user = self._users.get(user_id)
        return user if user is not None and user.tenant_id == tenant_id else None

    async def list_users(self, tenant_id: UUID) -> list[UserRecord]:
        return [u for u in self._users.values() if u.tenant_id == tenant_id]

    async def add_user(self, user: UserRecord) -> None:
        if await self.user_by_email(user.tenant_id, user.email) is not None:
            raise AccountConflictError("That address already has an account in this workspace.")
        self._users[user.id] = user

    async def set_password_hash(self, tenant_id: UUID, user_id: UUID, password_hash: str) -> None:
        user = await self.user_by_id(tenant_id, user_id)
        if user is not None:
            self._users[user_id] = replace(user, password_hash=password_hash)

    async def update_user(
        self, tenant_id: UUID, user_id: UUID, *, role: str | None = None, status: str | None = None
    ) -> UserRecord | None:
        user = await self.user_by_id(tenant_id, user_id)
        if user is None:
            return None
        updated = replace(
            user,
            role=UserRole(role) if role is not None else user.role,
            status=UserStatus(status) if status is not None else user.status,
        )
        self._users[user_id] = updated
        return updated

    async def count_active_admins(self, tenant_id: UUID) -> int:
        return sum(
            1
            for u in self._users.values()
            if u.tenant_id == tenant_id and u.role is UserRole.ADMIN and u.is_active
        )

    # --- sessions -----------------------------------------------------------------------------
    async def add_session(self, session: SessionRecord) -> None:
        self._sessions[session.id] = session

    async def get_session(self, tenant_id: UUID, token_hash: str) -> SessionRecord | None:
        return next(
            (s for s in self._sessions.values() if s.tenant_id == tenant_id and s.token_hash == token_hash),
            None,
        )

    async def claim_session(self, tenant_id: UUID, session_id: UUID, now: datetime) -> bool:
        session = self._sessions.get(session_id)
        if (
            session is None
            or session.tenant_id != tenant_id
            or session.rotated_at is not None
            or session.revoked_at is not None
        ):
            return False
        self._sessions[session_id] = replace(session, rotated_at=now)
        return True

    async def revoke_family(self, tenant_id: UUID, family_id: UUID, now: datetime) -> None:
        for sid, s in list(self._sessions.items()):
            if s.tenant_id == tenant_id and s.family_id == family_id and s.revoked_at is None:
                self._sessions[sid] = replace(s, revoked_at=now)

    async def revoke_user_sessions(self, tenant_id: UUID, user_id: UUID, now: datetime) -> None:
        for sid, s in list(self._sessions.items()):
            if s.tenant_id == tenant_id and s.user_id == user_id and s.revoked_at is None:
                self._sessions[sid] = replace(s, revoked_at=now)

    # --- invites ------------------------------------------------------------------------------
    async def add_invite(self, invite: InviteRecord) -> None:
        if invite.kind is InviteKind.INVITE and any(
            i.tenant_id == invite.tenant_id
            and i.kind is InviteKind.INVITE
            and i.email.lower() == invite.email.lower()
            and i.accepted_at is None
            and i.revoked_at is None
            for i in self._invites.values()
        ):
            raise AccountConflictError("That address already has a pending invite.")
        self._invites[invite.id] = invite

    async def get_invite(self, tenant_id: UUID, token_hash: str) -> InviteRecord | None:
        return next(
            (i for i in self._invites.values() if i.tenant_id == tenant_id and i.token_hash == token_hash),
            None,
        )

    async def get_invite_by_id(self, tenant_id: UUID, invite_id: UUID) -> InviteRecord | None:
        invite = self._invites.get(invite_id)
        return invite if invite is not None and invite.tenant_id == tenant_id else None

    async def list_pending_invites(self, tenant_id: UUID, now: datetime) -> list[InviteRecord]:
        return sorted(
            (i for i in self._invites.values() if i.tenant_id == tenant_id and i.is_usable(now)),
            key=lambda i: i.created_at or now,
            reverse=True,
        )

    async def claim_invite(self, tenant_id: UUID, invite_id: UUID, now: datetime) -> bool:
        invite = await self.get_invite_by_id(tenant_id, invite_id)
        if invite is None or not invite.is_usable(now):
            return False
        self._invites[invite_id] = replace(invite, accepted_at=now)
        return True

    async def revoke_invite(self, tenant_id: UUID, invite_id: UUID, now: datetime) -> bool:
        invite = await self.get_invite_by_id(tenant_id, invite_id)
        if invite is None or invite.accepted_at is not None or invite.revoked_at is not None:
            return False
        self._invites[invite_id] = replace(invite, revoked_at=now)
        return True

    async def revoke_invites_for_user(self, tenant_id: UUID, user_id: UUID, now: datetime) -> None:
        for iid, i in list(self._invites.items()):
            if (
                i.tenant_id == tenant_id
                and i.user_id == user_id
                and i.accepted_at is None
                and i.revoked_at is None
            ):
                self._invites[iid] = replace(i, revoked_at=now)
