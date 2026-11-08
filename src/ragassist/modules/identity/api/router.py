"""Authentication stub router for dev/test environment."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
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
async def generate_dev_token(req: TokenRequest) -> TokenResponse:
    """Generate a valid JWT with tenant_id, user_id, and role claims."""
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

