"""Authentication stub router for dev/test environment."""

from hmac import compare_digest
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from ragassist.shared.config.settings import get_settings
from ragassist.shared.domain import TenantId, UserId
from ragassist.shared.security.jwt import UserRole, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


class TokenRequest(BaseModel):
    user_id: UUID
    tenant_id: UUID
    role: UserRole = UserRole.USER


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    tenant_id: UUID
    role: str


@router.post("/token", response_model=TokenResponse)
async def generate_dev_token(
    req: TokenRequest, x_dev_auth_secret: str | None = Header(default=None)
) -> TokenResponse:
    """Generate a valid JWT with tenant_id, user_id, and role claims.

    Development and test only, and only for a caller that knows ``DEV_AUTH_SECRET`` (sent as ``X-Dev-Auth-Secret``):
    the environment flag alone would let anyone who can reach a development stack sign in as any tenant's admin.
    """
    settings = get_settings()
    if settings.APP_ENV not in ("development", "test"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development token issuance is disabled in this environment",
        )
    if not compare_digest((x_dev_auth_secret or "").encode(), settings.DEV_AUTH_SECRET.encode()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="A valid X-Dev-Auth-Secret header is required"
        )
    token = create_access_token(
        user_id=UserId(req.user_id),
        tenant_id=TenantId(req.tenant_id),
        role=req.role,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        role=req.role.value,
    )

