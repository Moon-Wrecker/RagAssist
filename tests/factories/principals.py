"""Builders for identities and JWTs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from support.spec import TEST_SECRET_KEY

from ragassist.shared.domain import TenantId, UserId
from ragassist.shared.security.jwt import Principal, UserRole, create_access_token


def new_tenant() -> TenantId:
    return TenantId(uuid4())


def new_user() -> UserId:
    return UserId(uuid4())


def make_token(
    *,
    role: UserRole = UserRole.USER,
    tenant_id: TenantId | UUID | None = None,
    user_id: UserId | UUID | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """A validly signed token (signed with the active ``Settings.SECRET_KEY``)."""
    return create_access_token(
        user_id=UserId(user_id or uuid4()),
        tenant_id=TenantId(tenant_id or uuid4()),
        role=role,
        expires_delta=expires_delta,
    )


def make_principal(
    *,
    role: UserRole = UserRole.USER,
    tenant_id: TenantId | UUID | None = None,
    user_id: UserId | UUID | None = None,
) -> Principal:
    tenant = TenantId(tenant_id or uuid4())
    user = UserId(user_id or uuid4())
    token = make_token(role=role, tenant_id=tenant, user_id=user)
    return Principal(user_id=user, tenant_id=tenant, role=role, raw_token=token)


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def forge_token(
    *,
    key: str = TEST_SECRET_KEY,
    algorithm: str = "HS256",
    claims: dict[str, Any] | None = None,
    drop: tuple[str, ...] = (),
    expired: bool = False,
) -> str:
    """Hand-build a token for attack tests (wrong key, missing claims, expired, ``alg=none``...).

    Defaults produce a token that *would* be valid; each argument breaks exactly one thing.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(uuid4()),
        "tenant_id": str(uuid4()),
        "role": UserRole.USER.value,
        "iat": now,
        "exp": now + (timedelta(minutes=-5) if expired else timedelta(minutes=5)),
    }
    payload.update(claims or {})
    for claim in drop:
        payload.pop(claim, None)
    if algorithm == "none":
        return jwt.encode(payload, key=None, algorithm="none")  # type: ignore[arg-type]
    return jwt.encode(payload, key, algorithm=algorithm)
