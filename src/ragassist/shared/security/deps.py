"""FastAPI authentication and tenant principal dependencies."""

from collections.abc import AsyncGenerator
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from ragassist.shared.db.session import get_db_session
from ragassist.shared.db.uow import UnitOfWork
from ragassist.shared.security.jwt import Principal, UserRole, decode_access_token
from sqlalchemy.ext.asyncio import AsyncSession

_bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme),
) -> Principal:
    """Extract and verify Principal from Authorization: Bearer <token>."""
    try:
        return decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_role(*roles: UserRole):
    """Enforce allowed roles on route handlers."""
    async def _role_checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{principal.role.value}' is not permitted for this action.",
            )
        return principal
    return _role_checker


async def get_tenant_uow(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[UnitOfWork, None]:
    """Provide a UnitOfWork scoped and locked to the authenticated tenant."""
    async with UnitOfWork(session, principal.tenant_id) as uow:
        yield uow

