"""Opaque one-time tokens of the form ``{tenant_id}.{random}``.

The tenant id leads the token so the store can open the right row-level-security scope *before* looking the token
up. It is not a secret and grants nothing; all the strength is in the random part (256 bits from ``secrets``). Only
the SHA-256 of that part is stored, so a database read cannot be replayed as a token. A fast hash is correct here:
the input is high-entropy, so there is nothing to brute-force, unlike a password.
"""

from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

from ragassist.modules.identity.domain.errors import InvalidTokenError

_RANDOM_BYTES = 32
_MAX_TOKEN_LENGTH = 200


def hash_secret(random_part: str) -> str:
    return hashlib.sha256(random_part.encode("utf-8")).hexdigest()


def issue_token(tenant_id: UUID) -> tuple[str, str]:
    """Return ``(token, token_hash)``. Hand out the token once; keep only the hash."""
    random_part = secrets.token_urlsafe(_RANDOM_BYTES)
    return f"{tenant_id}.{random_part}", hash_secret(random_part)


def parse_token(token: str) -> tuple[UUID, str]:
    """Split a token into ``(tenant_id, token_hash)``; any malformed value is an ``InvalidTokenError``."""
    if not token or len(token) > _MAX_TOKEN_LENGTH or token.count(".") != 1:
        raise InvalidTokenError("Invalid or expired link.")
    tenant_part, random_part = token.split(".", 1)
    try:
        tenant_id = UUID(tenant_part)
    except ValueError as exc:
        raise InvalidTokenError("Invalid or expired link.") from exc
    if not random_part:
        raise InvalidTokenError("Invalid or expired link.")
    return tenant_id, hash_secret(random_part)
