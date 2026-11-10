"""Builds the identity services from the settings and a store (Postgres in the runtime, in-memory in tests)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ragassist.modules.identity.adapters.argon2_hasher import Argon2PasswordHasher
from ragassist.modules.identity.application import (
    AccountService,
    AuthPolicy,
    AuthService,
    IdentityStore,
    LoginThrottle,
    PasswordHasher,
)
from ragassist.modules.identity.application.auth_service import utcnow
from ragassist.shared.config.settings import Settings
from ragassist.shared.counters import SharedCounters


@dataclass(frozen=True)
class IdentityServices:
    store: IdentityStore
    auth: AuthService
    accounts: AccountService
    policy: AuthPolicy


def build_identity(
    settings: Settings,
    store: IdentityStore,
    hasher: PasswordHasher | None = None,
    *,
    clock: Callable[[], datetime] = utcnow,
    throttle: LoginThrottle | None = None,
    shared_counters: SharedCounters | None = None,
) -> IdentityServices:
    policy = AuthPolicy.from_settings(settings)
    hasher = hasher or Argon2PasswordHasher()
    throttle = throttle or LoginThrottle(
        max_failures=settings.AUTH_LOGIN_MAX_FAILURES,
        max_per_ip=settings.AUTH_LOGIN_MAX_PER_IP,
        window_seconds=settings.AUTH_LOGIN_WINDOW_SECONDS,
        shared=shared_counters,
    )
    auth = AuthService(store, hasher, policy, throttle, clock=clock)
    return IdentityServices(
        store=store,
        auth=auth,
        accounts=AccountService(store, hasher, policy, auth, clock=clock),
        policy=policy,
    )
