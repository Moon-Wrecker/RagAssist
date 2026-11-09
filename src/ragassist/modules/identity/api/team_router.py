"""Team management for workspace administrators: members, roles, invitations and password-reset links.

Every route is admin-only (``require_role``) and acts on the administrator's own tenant, taken from the verified
token. Links are returned once, in the response, because the server stores only their hash.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from ragassist.modules.identity.api.deps import get_identity, http_error
from ragassist.modules.identity.api.schemas import (
    InviteOut,
    InviteRequest,
    IssuedLinkOut,
    MemberOut,
    MemberPatch,
)
from ragassist.modules.identity.domain import UserStatus
from ragassist.modules.identity.wiring import IdentityServices
from ragassist.shared.domain import DomainError
from ragassist.shared.security.deps import require_role
from ragassist.shared.security.jwt import Principal, UserRole

router = APIRouter(prefix="/team", tags=["Team"])

AdminOnly = Depends(require_role(UserRole.ADMIN))


@router.get("/members", response_model=list[MemberOut], summary="Everyone in the workspace")
async def list_members(
    principal: Principal = AdminOnly, identity: IdentityServices = Depends(get_identity)
) -> list[MemberOut]:
    return [MemberOut.of(u) for u in await identity.accounts.list_members(principal.tenant_id)]


@router.patch("/members/{user_id}", response_model=MemberOut, summary="Change a member's role or status")
async def change_member(
    user_id: UUID,
    body: MemberPatch,
    principal: Principal = AdminOnly,
    identity: IdentityServices = Depends(get_identity),
) -> MemberOut:
    try:
        updated = await identity.accounts.change_member(
            principal.tenant_id,
            principal.user_id,
            user_id,
            role=body.role,
            status=UserStatus(body.status) if body.status else None,
        )
    except DomainError as exc:
        raise http_error(exc) from exc
    return MemberOut.of(updated)


@router.post(
    "/members/{user_id}/reset-link",
    response_model=IssuedLinkOut,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a one-time password-reset link for a member",
)
async def issue_reset_link(
    user_id: UUID, principal: Principal = AdminOnly, identity: IdentityServices = Depends(get_identity)
) -> IssuedLinkOut:
    try:
        link = await identity.accounts.reset_link(principal.tenant_id, principal.user_id, user_id)
    except DomainError as exc:
        raise http_error(exc) from exc
    return IssuedLinkOut.of(link)


@router.get("/invites", response_model=list[InviteOut], summary="Pending invitations and reset links")
async def list_invites(
    principal: Principal = AdminOnly, identity: IdentityServices = Depends(get_identity)
) -> list[InviteOut]:
    return [InviteOut.of(i) for i in await identity.accounts.list_invites(principal.tenant_id)]


@router.post(
    "/invites",
    response_model=IssuedLinkOut,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a person by email; returns the one-time link to give them",
)
async def create_invite(
    body: InviteRequest, principal: Principal = AdminOnly, identity: IdentityServices = Depends(get_identity)
) -> IssuedLinkOut:
    try:
        link = await identity.accounts.invite(principal.tenant_id, principal.user_id, body.email, body.role)
    except DomainError as exc:
        raise http_error(exc) from exc
    return IssuedLinkOut.of(link)


@router.delete(
    "/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a pending invitation"
)
async def revoke_invite(
    invite_id: UUID, principal: Principal = AdminOnly, identity: IdentityServices = Depends(get_identity)
) -> None:
    try:
        await identity.accounts.revoke_invite(principal.tenant_id, invite_id)
    except DomainError as exc:
        raise http_error(exc) from exc
