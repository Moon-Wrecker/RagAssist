"""Workspaces, invitations, password links and team management.

Goal: let an operator create a workspace, let an administrator add and manage people, and let a person set their
own password, without any email service and without a password ever being chosen by someone else.

Decisions (ADR 0007):
* No default passwords exist anywhere. Every account starts with no password and gets one through a single-use,
  expiring link. The link carries a 256-bit secret in the URL *fragment* (``/accept#token=...``), which browsers do
  not send to servers, so it stays out of access logs.
* The administrator sees the link once and hands it over; the database keeps only its hash.
* An administrator cannot change their own role or status, and the last active administrator cannot be removed.
  Disabling an account revokes its refresh sessions and pending links at once; an access token already issued
  lives until it expires (minutes).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import structlog

from ragassist.modules.identity.application.auth_service import AuthPolicy, AuthService, SignedIn, utcnow
from ragassist.modules.identity.application.ports import IdentityStore, PasswordHasher
from ragassist.modules.identity.domain import (
    InvalidTokenError,
    InviteKind,
    InviteRecord,
    LastAdminError,
    SelfChangeError,
    UserRecord,
    UserStatus,
    Workspace,
    issue_token,
    normalise_email,
    parse_token,
    validate_password,
    validate_slug,
)
from ragassist.modules.identity.domain.errors import AccountConflictError
from ragassist.shared.domain import EntityNotFoundError, ValidationError
from ragassist.shared.security.jwt import UserRole

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class IssuedLink:
    """A link to hand to a person. ``url`` is shown once; only its hash is stored."""

    invite_id: UUID
    kind: InviteKind
    email: str
    role: UserRole
    url: str
    expires_at: datetime


class AccountService:
    def __init__(
        self,
        store: IdentityStore,
        hasher: PasswordHasher,
        policy: AuthPolicy,
        auth: AuthService,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._store = store
        self._hasher = hasher
        self._policy = policy
        self._auth = auth
        self._clock = clock

    # --- operator: create a workspace ---------------------------------------------------------
    async def create_workspace(self, name: str, slug: str, admin_email: str) -> tuple[Workspace, IssuedLink]:
        """Create the workspace and its first administrator (no password yet) and return their set-up link."""
        clean_name = (name or "").strip()
        if not 1 <= len(clean_name) <= 255:
            raise ValidationError("A workspace needs a name (up to 255 characters).")
        workspace = Workspace(id=uuid4(), name=clean_name, slug=validate_slug(slug))
        email = normalise_email(admin_email)
        admin = UserRecord(
            id=uuid4(),
            tenant_id=workspace.id,
            email=email,
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        await self._store.create_workspace(workspace, admin)
        link = await self._issue(admin.tenant_id, InviteKind.RESET, email, admin.role, user_id=admin.id)
        return workspace, link

    async def setup_link_for(self, tenant_id: UUID, user_id: UUID) -> IssuedLink:
        """A fresh set-password link for an existing account (used by the operator CLI)."""
        user = await self._store.user_by_id(tenant_id, user_id)
        if user is None:
            raise EntityNotFoundError("No such account.")
        return await self._reset_link(user, created_by=None)

    # --- administrator: team ------------------------------------------------------------------
    async def list_members(self, tenant_id: UUID) -> list[UserRecord]:
        return sorted(await self._store.list_users(tenant_id), key=lambda u: u.email)

    async def list_invites(self, tenant_id: UUID) -> list[InviteRecord]:
        return await self._store.list_pending_invites(tenant_id, self._clock())

    async def invite(self, tenant_id: UUID, created_by: UUID, email: str, role: UserRole) -> IssuedLink:
        address = normalise_email(email)
        if await self._store.user_by_email(tenant_id, address) is not None:
            raise AccountConflictError("That address already has an account in this workspace.")
        return await self._issue(tenant_id, InviteKind.INVITE, address, role, created_by=created_by)

    async def reset_link(self, tenant_id: UUID, created_by: UUID, user_id: UUID) -> IssuedLink:
        user = await self._store.user_by_id(tenant_id, user_id)
        if user is None:
            raise EntityNotFoundError("No such member.")
        return await self._reset_link(user, created_by=created_by)

    async def revoke_invite(self, tenant_id: UUID, invite_id: UUID) -> None:
        if not await self._store.revoke_invite(tenant_id, invite_id, self._clock()):
            raise EntityNotFoundError("No such pending invite.")

    async def change_member(
        self,
        tenant_id: UUID,
        acting_user_id: UUID,
        user_id: UUID,
        *,
        role: UserRole | None = None,
        status: UserStatus | None = None,
    ) -> UserRecord:
        if user_id == acting_user_id:
            raise SelfChangeError("You cannot change your own role or status.")
        target = await self._store.user_by_id(tenant_id, user_id)
        if target is None:
            raise EntityNotFoundError("No such member.")
        new_role = role or target.role
        new_status = status or target.status
        removes_an_admin = (
            target.role is UserRole.ADMIN
            and target.is_active
            and (new_role is not UserRole.ADMIN or new_status is not UserStatus.ACTIVE)
        )
        if removes_an_admin and await self._store.count_active_admins(tenant_id) <= 1:
            raise LastAdminError("A workspace needs at least one active administrator.")
        updated = await self._store.update_user(
            tenant_id, user_id, role=new_role.value, status=new_status.value
        )
        if updated is None:
            raise EntityNotFoundError("No such member.")
        if new_status is UserStatus.DISABLED:
            now = self._clock()
            await self._store.revoke_user_sessions(tenant_id, user_id, now)
            await self._store.revoke_invites_for_user(tenant_id, user_id, now)
        return updated

    # --- anyone with a link ---------------------------------------------------------------------
    async def accept(self, token: str, password: str) -> SignedIn:
        """Spend a link: set the password (creating the account for an invite) and sign the person in."""
        tenant_id, token_hash = parse_token(token)
        now = self._clock()
        invite = await self._store.get_invite(tenant_id, token_hash)
        if invite is None or not invite.is_usable(now):
            raise InvalidTokenError("This link is invalid or has expired.")
        validate_password(password, min_length=self._policy.password_min_length, email=invite.email)
        if not await self._store.claim_invite(tenant_id, invite.id, now):
            raise InvalidTokenError("This link is invalid or has expired.")

        password_hash = await self._hasher.hash(password)
        if invite.kind is InviteKind.INVITE:
            user = UserRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                email=invite.email,
                role=invite.role,
                status=UserStatus.ACTIVE,
                password_hash=password_hash,
            )
            await self._store.add_user(user)
        else:
            if invite.user_id is None:
                raise InvalidTokenError("This link is invalid or has expired.")
            found = await self._store.user_by_id(tenant_id, invite.user_id)
            if found is None or not found.is_active:
                raise InvalidTokenError("This link is invalid or has expired.")
            await self._store.set_password_hash(tenant_id, found.id, password_hash)
            await self._store.revoke_user_sessions(tenant_id, found.id, now)  # a reset ends every session
            user = UserRecord(
                id=found.id,
                tenant_id=tenant_id,
                email=found.email,
                role=found.role,
                status=found.status,
                password_hash=password_hash,
            )
        workspace = await self._store.workspace_by_id(tenant_id)
        if workspace is None:
            raise InvalidTokenError("This link is invalid or has expired.")
        return await self._auth.start_session(user, workspace)

    # ------------------------------------------------------------------------------------------
    async def _reset_link(self, user: UserRecord, *, created_by: UUID | None) -> IssuedLink:
        await self._store.revoke_invites_for_user(user.tenant_id, user.id, self._clock())
        return await self._issue(
            user.tenant_id, InviteKind.RESET, user.email, user.role, user_id=user.id, created_by=created_by
        )

    async def _issue(
        self,
        tenant_id: UUID,
        kind: InviteKind,
        email: str,
        role: UserRole,
        *,
        user_id: UUID | None = None,
        created_by: UUID | None = None,
    ) -> IssuedLink:
        now = self._clock()
        token, token_hash = issue_token(tenant_id)
        invite = InviteRecord(
            id=uuid4(),
            tenant_id=tenant_id,
            kind=kind,
            email=email,
            role=role,
            token_hash=token_hash,
            expires_at=now + self._policy.invite_ttl,
            user_id=user_id,
            created_by=created_by,
            created_at=now,
        )
        await self._store.add_invite(invite)
        return IssuedLink(
            invite_id=invite.id,
            kind=kind,
            email=email,
            role=role,
            url=f"{self._policy.web_base_url}/accept#token={token}",
            expires_at=invite.expires_at,
        )
