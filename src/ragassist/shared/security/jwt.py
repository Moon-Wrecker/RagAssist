"""Security, JWT authentication, and caller Principal context."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID
import jwt
from pydantic import BaseModel
from ragassist.shared.config.settings import get_settings
from ragassist.shared.domain import TenantId, UserId


class UserRole(str, Enum):
    """User authorization roles."""

    USER = "user"
    ADMIN = "admin"
    AGENT = "agent"


@dataclass(frozen=True)
class Principal:
    """Verified identity extracted from a validated JWT."""

    user_id: UserId
    tenant_id: TenantId
    role: UserRole
    raw_token: str

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_agent(self) -> bool:
        return self.role == UserRole.AGENT


class TokenPayload(BaseModel):
    """Structured JWT claims."""

    sub: str  # user_id
    tenant_id: str
    role: str
    exp: datetime
    iat: datetime


def create_access_token(
    user_id: UserId,
    tenant_id: TenantId,
    role: UserRole,
    expires_delta: timedelta | None = None,
) -> str:
    """Generate a signed JWT token."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    claims = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role.value,
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(
        claims,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Principal:
    """Decode and validate a JWT token into a Principal."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = UserId(UUID(payload["sub"]))
        tenant_id = TenantId(UUID(payload["tenant_id"]))
        role = UserRole(payload.get("role", UserRole.USER.value))
        return Principal(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            raw_token=token,
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise ValueError(f"Invalid or expired authentication token: {exc}") from exc

