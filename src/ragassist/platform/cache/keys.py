"""Cache key construction: the one place a key is made, so the tenant rule holds by construction (ADR 0015).

Rule (AGENTS.md section 1.3, multi-tenant): a key always contains the ``tenant_id`` (and the role when the cached
result depends on who asks), and its variable part is a keyed hash of the *normalised* text, never the text itself,
a token or any personal data. ``CacheKeyBuilder.key`` has no way to omit the tenant: ``tenant_id`` is a required
positional argument and an empty or malformed one raises. Two tenants (or two roles) can therefore never produce the
same key, whatever the text, so a hit cannot cross them.

Layout: ``{prefix}:v1:{tenant}:{kind}:{role}:{hash}[:{part}...]``. The tenant comes first so a whole tenant (or one
kind of its entries) is a prefix and can be purged with ``delete_prefix``.

The hash is HMAC-SHA256 with a key derived from ``SECRET_KEY``: unlike a bare SHA-256 it cannot be reversed by
guessing short questions if someone reads the cache's keys, and a rotated secret simply starts a new key space.
Normalisation (NFKC, case-fold, collapsed whitespace) makes "Reset  my PASSWORD" and "reset my password" one entry.

Consulted: Python ``hmac`` and ``unicodedata`` documentation; OWASP guidance to never put identifiers or secrets that
are not needed in cache keys.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata

KEY_VERSION = "v1"

#: Kinds of tenant-scoped entries. Part of the key, so a purge can target one kind.
EMBEDDING_QUERY = "embq"
EMBEDDING_DOCUMENT = "embd"
RETRIEVAL = "ret"
DECISION = "dec"
CORPUS = "corpus"

_TENANT = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_ROLE = re.compile(r"^[a-z_]{1,32}$")
_PART = re.compile(r"[^A-Za-z0-9._-]")
_KIND = re.compile(r"^[a-z0-9]{1,16}$")
_PREFIX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_DERIVATION_LABEL = b"ragassist-cache-key-v1"


class InvalidCacheKey(ValueError):
    """A key part is missing or malformed (most importantly: no tenant)."""


def normalise_text(text: str) -> str:
    """Canonical form of a question or passage for keying: NFKC, case-folded, whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class CacheKeyBuilder:
    def __init__(self, *, prefix: str, secret: str | bytes) -> None:
        if not _PREFIX.match(prefix):
            raise InvalidCacheKey("the key prefix must be letters, digits, '_' or '-'")
        raw = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not raw:
            raise InvalidCacheKey("a hashing secret is required")
        self._prefix = prefix
        self._hmac_key = hmac.new(raw, _DERIVATION_LABEL, hashlib.sha256).digest()

    def digest(self, text: str, *context: str) -> str:
        """HMAC of the normalised text plus context strings (provider, model, k ...), as 64 hex characters."""
        material = "\x00".join([normalise_text(text), *context]).encode("utf-8")
        return hmac.new(self._hmac_key, material, hashlib.sha256).hexdigest()

    def tenant_prefix(self, tenant_id: object, kind: str | None = None) -> str:
        """Prefix shared by every key of a tenant (optionally of one kind); what a purge deletes."""
        tenant = self._tenant(tenant_id)
        base = f"{self._prefix}:{KEY_VERSION}:{tenant}:"
        return base if kind is None else f"{base}{self._kind(kind)}:"

    def key(
        self,
        kind: str,
        tenant_id: object,
        *,
        role: str | None = None,
        text: str | None = None,
        context: tuple[str, ...] = (),
        parts: tuple[str, ...] = (),
    ) -> str:
        """The key of one entry. ``text`` is hashed; ``context`` feeds the hash; ``parts`` are short safe labels."""
        segments = [self.tenant_prefix(tenant_id, kind).rstrip(":")]
        segments.append(self._role(role))
        if text is not None:
            segments.append(self.digest(text, *context))
        elif context:
            raise InvalidCacheKey("context without text would put raw values in the key")
        segments.extend(_PART.sub("_", part)[:64] for part in parts)
        return ":".join(segments)

    def shared_counter_key(self, kind: str, *identifiers: str) -> str:
        """Key of a counter that is not tenant data (rate limits by client address or account); always hashed."""
        return f"{self._prefix}:{KEY_VERSION}:ctr:{self._kind(kind)}:{self.digest('', kind, *identifiers)}"

    # -- validation -----------------------------------------------------------------------------------------
    @staticmethod
    def _tenant(tenant_id: object) -> str:
        tenant = "" if tenant_id is None else str(tenant_id)
        if not _TENANT.match(tenant):
            raise InvalidCacheKey("a cache key needs a valid tenant id")
        return tenant

    @staticmethod
    def _role(role: str | None) -> str:
        if role is None:
            return "-"
        if not _ROLE.match(role):
            raise InvalidCacheKey("malformed role")
        return role

    @staticmethod
    def _kind(kind: str) -> str:
        if not _KIND.match(kind):
            raise InvalidCacheKey("malformed key kind")
        return kind
