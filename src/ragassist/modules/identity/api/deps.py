"""Dependencies and shared HTTP helpers of the identity routers."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response, status

from ragassist.modules.identity.domain import (
    AccountConflictError,
    AuthenticationError,
    InvalidTokenError,
    LastAdminError,
    PasswordPolicyError,
    RateLimitedError,
    SelfChangeError,
)
from ragassist.modules.identity.wiring import IdentityServices, build_identity
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.domain import DomainError, EntityNotFoundError, ValidationError

REFRESH_COOKIE = "ragassist_refresh"


def get_identity(request: Request) -> IdentityServices:
    """The identity services of this app: Postgres-backed once the runtime is up, in-memory otherwise."""
    services: IdentityServices | None = getattr(request.app.state, "identity", None)
    if services is None:
        from ragassist.modules.identity.adapters.memory import InMemoryIdentityStore
        from ragassist.runtime import active_runtime

        runtime = active_runtime()
        store = runtime.identity if runtime is not None else InMemoryIdentityStore()
        services = build_identity(get_settings(), store)
        request.app.state.identity = services
    return services


# --- refresh cookie ---------------------------------------------------------------------------
def cookie_path(settings: Settings) -> str:
    return f"{settings.API_V1_PREFIX}/auth"


def set_refresh_cookie(response: Response, token: str, max_age: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="strict",
        path=cookie_path(settings),
    )


def clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=REFRESH_COOKIE,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="strict",
        path=cookie_path(settings),
    )


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else url


def trusted_origins(settings: Settings) -> set[str]:
    return {_origin_of(o) for o in settings.CORS_ORIGINS} | {_origin_of(settings.WEB_BASE_URL)}


async def require_trusted_origin(request: Request) -> None:
    """CSRF guard for the endpoints that act on the refresh cookie: the browser must say it came from our app.

    ``SameSite=Strict`` already keeps the cookie off cross-site requests; this refuses the rest, including a
    request with no ``Origin`` at all (every browser sends one on a ``POST``).
    """
    origin = request.headers.get("origin")
    if origin is None or origin not in trusted_origins(get_settings()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-origin request refused.")


# --- domain errors to HTTP --------------------------------------------------------------------
def http_error(exc: Exception) -> HTTPException:
    """Map an identity domain error to the HTTP error a client should see."""
    if isinstance(exc, RateLimitedError):
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, exc.message, headers={"Retry-After": str(exc.retry_after)}
        )
    if isinstance(exc, AuthenticationError):
        return HTTPException(status.HTTP_401_UNAUTHORIZED, exc.message)
    if isinstance(exc, InvalidTokenError):
        return HTTPException(status.HTTP_401_UNAUTHORIZED, exc.message)
    if isinstance(exc, PasswordPolicyError | ValidationError):
        return HTTPException(422, exc.message)
    if isinstance(exc, AccountConflictError | LastAdminError | SelfChangeError):
        return HTTPException(status.HTTP_409_CONFLICT, exc.message)
    if isinstance(exc, EntityNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, exc.message)
    if isinstance(exc, DomainError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, exc.message)
    raise exc
