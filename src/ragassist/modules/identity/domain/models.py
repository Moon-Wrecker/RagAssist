"""Identity records. Frozen: a change is a new value written through the store, never an in-place edit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ragassist.shared.security.jwt import UserRole


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class InviteKind(StrEnum):
    INVITE = "invite"  # creates a new account
    RESET = "reset"  # sets a new password on an existing account


@dataclass(frozen=True)
class Workspace:
    """A tenant as the person knows it: a name and the slug they type at sign-in."""

    id: UUID
    name: str
    slug: str


@dataclass(frozen=True)
class UserRecord:
    id: UUID
    tenant_id: UUID
    email: str
    role: UserRole
    status: UserStatus
    password_hash: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE

    @property
    def can_sign_in(self) -> bool:
        return self.is_active and bool(self.password_hash)


@dataclass(frozen=True)
class SessionRecord:
    """One refresh token. ``token_hash`` is the SHA-256 of its random part; the token itself is never stored."""

    id: UUID
    tenant_id: UUID
    user_id: UUID
    family_id: UUID
    token_hash: str
    expires_at: datetime
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class InviteRecord:
    """A one-time link that lets a person set a password (``invite`` creates the account, ``reset`` reuses it)."""

    id: UUID
    tenant_id: UUID
    kind: InviteKind
    email: str
    role: UserRole
    token_hash: str
    expires_at: datetime
    user_id: UUID | None = None
    created_by: UUID | None = None
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime | None = None

    def is_usable(self, now: datetime) -> bool:
        return self.accepted_at is None and self.revoked_at is None and self.expires_at > now
