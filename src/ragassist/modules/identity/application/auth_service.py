"""Sign-in, silent refresh, sign-out and "who am I".

Goal: turn a workspace slug, an email and a password into a short-lived access token (kept in browser memory) plus a
rotating refresh token (an httpOnly cookie), and keep that pair safe.

Decisions, each from the sources named in ``docs/adr/0007-accounts-and-sessions.md``:
* Unknown workspace, unknown email, disabled account and wrong password are indistinguishable: one message, and a
  dummy password verification on the "not found" paths so the response time does not reveal which one it was
  (OWASP Authentication Cheat Sheet).
* Refresh tokens rotate on every use. Presenting one that was already rotated means it was copied, so the whole login
  family is revoked (OWASP Session Management / the OAuth 2.0 Security BCP on refresh-token replay).
* The access token is the same signed JWT the rest of the API already verifies; ``Principal`` still comes only from
  its claims (AGENTS.md section 1.3).
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import structlog

from ragassist.modules.identity.application.ports import IdentityStore, PasswordHasher
from ragassist.modules.identity.application.throttle import LoginThrottle
from ragassist.modules.identity.domain import (
    MAX_PASSWORD_LENGTH,
    AuthenticationError,
    InvalidTokenError,
    SessionRecord,
    UserRecord,
    Workspace,
    issue_token,
    parse_token,
)
from ragassist.shared.config.settings import Settings
from ragassist.shared.domain import TenantId, UserId
from ragassist.shared.security.jwt import create_access_token

logger = structlog.get_logger(__name__)

GENERIC_FAILURE = "Invalid workspace, email or password."


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AuthPolicy:
    """Lifetimes and limits, read once from the settings."""

    access_ttl: timedelta
    refresh_ttl: timedelta
    invite_ttl: timedelta
    password_min_length: int
    web_base_url: str

    @classmethod
    def from_settings(cls, settings: Settings) -> AuthPolicy:
        return cls(
            access_ttl=timedelta(minutes=settings.AUTH_ACCESS_TOKEN_MINUTES),
            refresh_ttl=timedelta(days=settings.AUTH_REFRESH_TOKEN_DAYS),
            invite_ttl=timedelta(hours=settings.AUTH_INVITE_HOURS),
            password_min_length=settings.AUTH_MIN_PASSPHRASE_LENGTH,
            web_base_url=settings.WEB_BASE_URL.rstrip("/"),
        )


@dataclass(frozen=True)
class SignedIn:
    """The outcome of a login or a refresh: what the browser keeps in memory and what goes in the cookie."""

    access_token: str
    expires_in: int
    refresh_token: str
    refresh_max_age: int
    user: UserRecord
    workspace: Workspace


class AuthService:
    def __init__(
        self,
        store: IdentityStore,
        hasher: PasswordHasher,
        policy: AuthPolicy,
        throttle: LoginThrottle,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._store = store
        self._hasher = hasher
        self._policy = policy
        self._throttle = throttle
        self._clock = clock
        self._dummy_hash: str | None = None

    # ------------------------------------------------------------------------------------------
    async def login(self, workspace_slug: str, email: str, password: str, client_ip: str) -> SignedIn:
        slug = (workspace_slug or "").strip().lower()
        address = (email or "").strip().lower()
        self._throttle.check(client_ip, slug, address)

        workspace = await self._store.workspace_by_slug(slug) if slug else None
        user = await self._store.user_by_email(workspace.id, address) if workspace and address else None
        real = user is not None and user.can_sign_in

        # Always spend one verification, so a missing account costs the same as a wrong password.
        stored = user.password_hash if real and user and user.password_hash else await self._dummy()
        candidate = password if len(password) <= MAX_PASSWORD_LENGTH else ""
        matched = await self._hasher.verify(stored, candidate)

        if not (real and matched) or user is None or workspace is None:
            self._throttle.record_failure(slug, address)
            raise AuthenticationError(GENERIC_FAILURE)

        self._throttle.record_success(slug, address)
        if user.password_hash and self._hasher.needs_rehash(user.password_hash):
            await self._store.set_password_hash(user.tenant_id, user.id, await self._hasher.hash(password))
        return await self.start_session(user, workspace)

    async def refresh(self, refresh_token: str) -> SignedIn:
        tenant_id, token_hash = parse_token(refresh_token)
        now = self._clock()
        session = await self._store.get_session(tenant_id, token_hash)
        if session is None:
            raise InvalidTokenError("Session expired. Sign in again.")
        if session.rotated_at is not None or session.revoked_at is not None:
            # A token that was already used or revoked is being replayed: assume it leaked, end the family.
            await self._store.revoke_family(tenant_id, session.family_id, now)
            logger.warning("auth.refresh_replay", tenant_id=str(tenant_id), user_id=str(session.user_id))
            raise InvalidTokenError("Session expired. Sign in again.")
        if session.expires_at <= now:
            raise InvalidTokenError("Session expired. Sign in again.")
        if not await self._store.claim_session(tenant_id, session.id, now):
            await self._store.revoke_family(tenant_id, session.family_id, now)  # lost a race to another use
            raise InvalidTokenError("Session expired. Sign in again.")

        user = await self._store.user_by_id(tenant_id, session.user_id)
        workspace = await self._store.workspace_by_id(tenant_id)
        if user is None or workspace is None or not user.is_active:
            await self._store.revoke_family(tenant_id, session.family_id, now)
            raise InvalidTokenError("Session expired. Sign in again.")
        return await self.start_session(user, workspace, family_id=session.family_id)

    async def logout(self, refresh_token: str) -> None:
        """End the session this token belongs to. Always succeeds from the caller's point of view."""
        try:
            tenant_id, token_hash = parse_token(refresh_token)
        except InvalidTokenError:
            return
        session = await self._store.get_session(tenant_id, token_hash)
        if session is not None:
            await self._store.revoke_family(tenant_id, session.family_id, self._clock())

    async def me(self, tenant_id: UUID, user_id: UUID) -> tuple[UserRecord, Workspace]:
        user = await self._store.user_by_id(tenant_id, user_id)
        workspace = await self._store.workspace_by_id(tenant_id)
        if user is None or workspace is None or not user.is_active:
            raise AuthenticationError("Your account is no longer active.")
        return user, workspace

    # ------------------------------------------------------------------------------------------
    async def start_session(
        self, user: UserRecord, workspace: Workspace, *, family_id: UUID | None = None
    ) -> SignedIn:
        """Issue an access token and a fresh refresh token for ``user`` (a new family unless rotating one)."""
        now = self._clock()
        refresh_token, token_hash = issue_token(user.tenant_id)
        await self._store.add_session(
            SessionRecord(
                id=uuid4(),
                tenant_id=user.tenant_id,
                user_id=user.id,
                family_id=family_id or uuid4(),
                token_hash=token_hash,
                expires_at=now + self._policy.refresh_ttl,
            )
        )
        access = create_access_token(
            user_id=UserId(user.id),
            tenant_id=TenantId(user.tenant_id),
            role=user.role,
            expires_delta=self._policy.access_ttl,
        )
        return SignedIn(
            access_token=access,
            expires_in=int(self._policy.access_ttl.total_seconds()),
            refresh_token=refresh_token,
            refresh_max_age=int(self._policy.refresh_ttl.total_seconds()),
            user=user,
            workspace=workspace,
        )

    async def _dummy(self) -> str:
        if self._dummy_hash is None:
            self._dummy_hash = await self._hasher.hash(secrets.token_urlsafe(24))
        return self._dummy_hash
