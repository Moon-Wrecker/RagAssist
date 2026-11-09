"""HTTP request and response models of the identity routers. No password hash ever appears in a response."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ragassist.modules.identity.application import IssuedLink, SignedIn
from ragassist.modules.identity.domain import InviteRecord, UserRecord, Workspace
from ragassist.shared.security.jwt import UserRole


class LoginRequest(BaseModel):
    workspace: str = Field(max_length=100, description="The workspace slug.")
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class AcceptRequest(BaseModel):
    token: str = Field(max_length=200, description="The token from the invite or reset link.")
    password: str = Field(max_length=1024)


class WorkspaceOut(BaseModel):
    id: UUID
    name: str
    slug: str

    @classmethod
    def of(cls, workspace: Workspace) -> WorkspaceOut:
        return cls(id=workspace.id, name=workspace.name, slug=workspace.slug)


class UserOut(BaseModel):
    id: UUID
    email: str
    role: UserRole
    status: str

    @classmethod
    def of(cls, user: UserRecord) -> UserOut:
        return cls(id=user.id, email=user.email, role=user.role, status=user.status.value)


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the access token expires.")
    user: UserOut
    workspace: WorkspaceOut

    @classmethod
    def of(cls, signed_in: SignedIn) -> SessionOut:
        return cls(
            access_token=signed_in.access_token,
            expires_in=signed_in.expires_in,
            user=UserOut.of(signed_in.user),
            workspace=WorkspaceOut.of(signed_in.workspace),
        )


class MeOut(BaseModel):
    user: UserOut
    workspace: WorkspaceOut


class MemberOut(UserOut):
    has_password: bool

    @classmethod
    def of(cls, user: UserRecord) -> MemberOut:  # type: ignore[override]
        return cls(
            id=user.id,
            email=user.email,
            role=user.role,
            status=user.status.value,
            has_password=bool(user.password_hash),
        )


class MemberPatch(BaseModel):
    role: UserRole | None = None
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class InviteRequest(BaseModel):
    email: str = Field(max_length=254)
    role: UserRole = UserRole.USER


class InviteOut(BaseModel):
    id: UUID
    kind: str
    email: str
    role: UserRole
    expires_at: datetime
    created_at: datetime | None

    @classmethod
    def of(cls, invite: InviteRecord) -> InviteOut:
        return cls(
            id=invite.id,
            kind=invite.kind.value,
            email=invite.email,
            role=invite.role,
            expires_at=invite.expires_at,
            created_at=invite.created_at,
        )


class IssuedLinkOut(BaseModel):
    invite_id: UUID
    kind: str
    email: str
    role: UserRole
    url: str = Field(description="Shown once. Give it to the person; only its hash is stored.")
    expires_at: datetime

    @classmethod
    def of(cls, link: IssuedLink) -> IssuedLinkOut:
        return cls(
            invite_id=link.invite_id,
            kind=link.kind.value,
            email=link.email,
            role=link.role,
            url=link.url,
            expires_at=link.expires_at,
        )
