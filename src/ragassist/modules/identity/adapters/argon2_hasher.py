"""Argon2id password hashing (argon2-cffi), run on the bounded CPU executor.

Consulted: OWASP Password Storage Cheat Sheet (argon2id is the first choice), RFC 9106 and the argon2-cffi docs
(``PasswordHasher`` defaults to the RFC 9106 low-memory profile; ``check_needs_rehash`` flags hashes made with
older parameters so they upgrade on the next successful sign-in). Hashing is CPU- and memory-bound, so it goes
through ``run_cpu_bound`` (AGENTS.md section 1.4) rather than blocking the event loop.
"""

from __future__ import annotations

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from ragassist.shared.resilience import run_cpu_bound


class Argon2PasswordHasher:
    def __init__(self, hasher: _Argon2 | None = None) -> None:
        self._hasher = hasher or _Argon2()

    async def hash(self, password: str) -> str:
        return await run_cpu_bound(self._hasher.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        return await run_cpu_bound(self._verify, password_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return False

    def _verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):  # VerifyMismatchError is a VerificationError
            return False
