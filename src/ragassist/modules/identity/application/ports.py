"""Ports of the identity module. Adapters (Postgres, in-memory, argon2) implement these; use cases depend on them."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from ragassist.modules.identity.domain import (
    InviteRecord,
    SessionRecord,
    UserRecord,
    Workspace,
)


class PasswordHasher(Protocol):
    """Slow, salted password hashing. CPU-bound, so implementations run it off the event loop."""

    async def hash(self, password: str) -> str: ...

    async def verify(self, password_hash: str, password: str) -> bool:
        """``True`` only for a match; a malformed hash is simply a non-match."""
        ...

    def needs_rehash(self, password_hash: str) -> bool: ...


class IdentityStore(Protocol):
    """Everything the identity use cases read and write.

    Every method except ``workspace_by_slug`` is scoped to one tenant, and the Postgres adapter runs it inside
    that tenant's row-level-security scope.
    """

    async def workspace_by_slug(self, slug: str) -> Workspace | None: ...

    async def workspace_by_id(self, tenant_id: UUID) -> Workspace | None: ...

    async def create_workspace(self, workspace: Workspace, admin: UserRecord) -> None:
        """Insert the tenant and its first administrator atomically (``WorkspaceExistsError`` on a taken slug)."""
        ...

    # --- users -------------------------------------------------------------------------------
    async def user_by_email(self, tenant_id: UUID, email: str) -> UserRecord | None: ...

    async def user_by_id(self, tenant_id: UUID, user_id: UUID) -> UserRecord | None: ...

    async def list_users(self, tenant_id: UUID) -> list[UserRecord]: ...

    async def add_user(self, user: UserRecord) -> None:
        """``AccountConflictError`` when the address is already used in the workspace."""
        ...

    async def set_password_hash(self, tenant_id: UUID, user_id: UUID, password_hash: str) -> None: ...

    async def update_user(
        self, tenant_id: UUID, user_id: UUID, *, role: str | None = None, status: str | None = None
    ) -> UserRecord | None:
        """Change role and/or status; ``None`` when the user does not exist in the workspace."""
        ...

    async def count_active_admins(self, tenant_id: UUID) -> int: ...

    # --- refresh sessions --------------------------------------------------------------------
    async def add_session(self, session: SessionRecord) -> None: ...

    async def get_session(self, tenant_id: UUID, token_hash: str) -> SessionRecord | None: ...

    async def claim_session(self, tenant_id: UUID, session_id: UUID, now: datetime) -> bool:
        """Atomically mark a session rotated. ``False`` when it was already rotated or revoked (a replay)."""
        ...

    async def revoke_family(self, tenant_id: UUID, family_id: UUID, now: datetime) -> None: ...

    async def revoke_user_sessions(self, tenant_id: UUID, user_id: UUID, now: datetime) -> None: ...

    # --- invite and reset links --------------------------------------------------------------
    async def add_invite(self, invite: InviteRecord) -> None: ...

    async def get_invite(self, tenant_id: UUID, token_hash: str) -> InviteRecord | None: ...

    async def get_invite_by_id(self, tenant_id: UUID, invite_id: UUID) -> InviteRecord | None: ...

    async def list_pending_invites(self, tenant_id: UUID, now: datetime) -> list[InviteRecord]: ...

    async def claim_invite(self, tenant_id: UUID, invite_id: UUID, now: datetime) -> bool:
        """Atomically mark an invite accepted. ``False`` when it was already used, revoked or expired."""
        ...

    async def revoke_invite(self, tenant_id: UUID, invite_id: UUID, now: datetime) -> bool: ...

    async def revoke_invites_for_user(self, tenant_id: UUID, user_id: UUID, now: datetime) -> None: ...
