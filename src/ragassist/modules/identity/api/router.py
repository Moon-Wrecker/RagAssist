"""Authentication routes: sign-in, silent refresh, sign-out, "who am I", accepting a link, and the dev token stub.

The access token travels in the response body and lives in browser memory; the refresh token is an httpOnly,
``SameSite=Strict`` cookie scoped to this router's path, so script on the page can never read it.
"""

from __future__ import annotations

from hmac import compare_digest
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ragassist.modules.identity.api.deps import (
    REFRESH_COOKIE,
    clear_refresh_cookie,
    get_identity,
    http_error,
    require_trusted_origin,
    set_refresh_cookie,
)
from ragassist.modules.identity.api.schemas import (
    AcceptRequest,
    LoginRequest,
    MeOut,
    SessionOut,
    UserOut,
    WorkspaceOut,
)
from ragassist.modules.identity.domain import AuthenticationError, InvalidTokenError, RateLimitedError
from ragassist.modules.identity.wiring import IdentityServices
from ragassist.shared.config.settings import get_settings
from ragassist.shared.domain import DomainError, TenantId, UserId
from ragassist.shared.security.deps import get_current_principal
from ragassist.shared.security.jwt import Principal, UserRole, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post(
    "/login",
    response_model=SessionOut,
    summary="Sign in with workspace, email and password",
    responses={401: {"description": "Invalid workspace, email or password."}, 429: {"description": "Too many attempts."}},
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    identity: IdentityServices = Depends(get_identity),
) -> SessionOut:
    try:
        signed_in = await identity.auth.login(body.workspace, body.email, body.password, _client_ip(request))
    except (AuthenticationError, RateLimitedError) as exc:
        raise http_error(exc) from exc
    set_refresh_cookie(response, signed_in.refresh_token, signed_in.refresh_max_age)
    return SessionOut.of(signed_in)


@router.post(
    "/refresh",
    response_model=SessionOut,
    summary="Exchange the refresh cookie for a new access token (the cookie rotates)",
    dependencies=[Depends(require_trusted_origin)],
)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    identity: IdentityServices = Depends(get_identity),
) -> SessionOut | JSONResponse:
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    try:
        signed_in = await identity.auth.refresh(refresh_token)
    except InvalidTokenError as exc:
        # A refused cookie is dead (expired, revoked or replayed): clear it so the browser stops sending it.
        refused = JSONResponse({"detail": exc.message}, status_code=status.HTTP_401_UNAUTHORIZED)
        clear_refresh_cookie(refused)
        return refused
    set_refresh_cookie(response, signed_in.refresh_token, signed_in.refresh_max_age)
    return SessionOut.of(signed_in)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End this session and clear the refresh cookie",
    dependencies=[Depends(require_trusted_origin)],
)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    identity: IdentityServices = Depends(get_identity),
) -> None:
    if refresh_token:
        await identity.auth.logout(refresh_token)
    clear_refresh_cookie(response)


@router.get("/me", response_model=MeOut, summary="The signed-in user and their workspace")
async def me(
    principal: Principal = Depends(get_current_principal),
    identity: IdentityServices = Depends(get_identity),
) -> MeOut:
    try:
        user, workspace = await identity.auth.me(principal.tenant_id, principal.user_id)
    except AuthenticationError as exc:
        raise http_error(exc) from exc
    return MeOut(user=UserOut.of(user), workspace=WorkspaceOut.of(workspace))


@router.post(
    "/invites/accept",
    response_model=SessionOut,
    summary="Spend an invite or password-reset link: set a password and sign in",
    responses={401: {"description": "The link is invalid, used or expired."}, 422: {"description": "Password rejected."}},
)
async def accept_link(
    body: AcceptRequest,
    response: Response,
    identity: IdentityServices = Depends(get_identity),
) -> SessionOut:
    try:
        signed_in = await identity.accounts.accept(body.token, body.password)
    except DomainError as exc:
        raise http_error(exc) from exc
    set_refresh_cookie(response, signed_in.refresh_token, signed_in.refresh_max_age)
    return SessionOut.of(signed_in)


# --- development token stub (disabled outside development and test) ----------------------------
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
