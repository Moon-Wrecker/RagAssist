"""The real argon2id adapter (with cheap parameters so the test stays fast)."""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher

from ragassist.modules.identity.adapters.argon2_hasher import Argon2PasswordHasher


def cheap(**overrides: int) -> Argon2PasswordHasher:
    params = {"time_cost": 1, "memory_cost": 8, "parallelism": 1, **overrides}
    return Argon2PasswordHasher(PasswordHasher(**params))


async def test_it_hashes_with_argon2id_and_a_random_salt() -> None:
    hasher = cheap()
    password = secrets.token_urlsafe(16)
    first, second = await hasher.hash(password), await hasher.hash(password)
    assert first.startswith("$argon2id$") and first != second


async def test_verify_accepts_the_right_password_and_nothing_else() -> None:
    hasher = cheap()
    password = secrets.token_urlsafe(16)
    stored = await hasher.hash(password)
    assert await hasher.verify(stored, password) is True
    assert await hasher.verify(stored, password + "x") is False
    assert await hasher.verify(stored, "") is False


async def test_a_malformed_stored_hash_is_a_non_match_not_an_error() -> None:
    hasher = cheap()
    for junk in ("", "plain-text", "$argon2id$garbage", "$2b$12$abcdefghijklmnopqrstuv"):
        assert await hasher.verify(junk, "anything") is False


async def test_a_hash_made_with_weaker_parameters_is_flagged_for_upgrade() -> None:
    weak = await cheap().hash("a-password-0123456789")
    strong = Argon2PasswordHasher(PasswordHasher(time_cost=2, memory_cost=16, parallelism=1))
    assert strong.needs_rehash(weak) is True
    assert strong.needs_rehash(await strong.hash("a-password-0123456789")) is False
    assert strong.needs_rehash("not a hash") is False
