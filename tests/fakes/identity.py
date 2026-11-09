"""Fast stand-ins for the identity module's slow or time-dependent collaborators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ragassist.modules.identity.adapters.memory import InMemoryIdentityStore
from ragassist.modules.identity.wiring import IdentityServices, build_identity
from ragassist.shared.config.settings import Settings


class FakeHasher:
    """Instant, deterministic ``PasswordHasher``. Counts verifications so a test can assert that every sign-in
    path (found or not) spends exactly one."""

    def __init__(self) -> None:
        self.verify_calls = 0
        self.hash_calls = 0
        self.rehash_everything = False

    async def hash(self, password: str) -> str:
        self.hash_calls += 1
        return f"fake${password[::-1]}"

    async def verify(self, password_hash: str, password: str) -> bool:
        self.verify_calls += 1
        return password_hash == f"fake${password[::-1]}"

    def needs_rehash(self, password_hash: str) -> bool:
        return self.rehash_everything


class MutableClock:
    """A UTC ``datetime`` source that only moves when told to."""

    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2030, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)


def make_identity(
    settings: Settings, *, hasher: FakeHasher | None = None, clock: MutableClock | None = None
) -> tuple[IdentityServices, FakeHasher, MutableClock, InMemoryIdentityStore]:
    """Identity services on the in-memory store with a fast hasher and a controllable clock."""
    store = InMemoryIdentityStore()
    hasher = hasher or FakeHasher()
    clock = clock or MutableClock()
    return build_identity(settings, store, hasher, clock=clock), hasher, clock, store
