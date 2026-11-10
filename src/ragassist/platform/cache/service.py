"""Cache facade: JSON and vector codecs, per-kind hit/miss counters, corpus versions and failure isolation.

Callers use this, never an adapter, so that:

* a backend failure (Redis down) is a miss, logged and counted, never an error in a request;
* an undecodable or tampered value is a miss and is deleted;
* hits and misses are counted per kind of entry for ``/metrics``;
* a tenant's *corpus version* lives in one place. It is a random token stored under the tenant's key and mixed into
  every retrieval key. Changing a document replaces the token, so every older entry becomes unreachable at once
  (and is then also purged by prefix). If the token itself is evicted or expires, a *new* random token is minted,
  which can only cause misses: an old entry can never become valid again because tokens never repeat.

Nothing here stores a value without a TTL: the TTLs come from ``CacheTTLs`` (settings) and every ``set`` requires one.
"""

from __future__ import annotations

import json
import secrets
import struct
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import structlog

from ragassist.platform.cache import keys as K
from ragassist.platform.cache.keys import CacheKeyBuilder
from ragassist.platform.cache.ports import Cache, CacheError, CacheStats

logger = structlog.get_logger(__name__)

#: Pseudo-tenant of the corpus version for shared knowledge (rows with no tenant, visible to every tenant).
GLOBAL_CORPUS = "global"


@dataclass(frozen=True)
class CacheTTLs:
    """Seconds to live per kind of entry; built from the ``CACHE_*_TTL_SECONDS`` settings."""

    embedding_query: int
    embedding_document: int
    retrieval: int
    decision: int
    corpus_version: int


class CacheService:
    def __init__(self, cache: Cache, keys: CacheKeyBuilder, ttls: CacheTTLs) -> None:
        self.cache = cache
        self.keys = keys
        self.ttls = ttls
        self._hits: dict[str, int] = defaultdict(int)
        self._misses: dict[str, int] = defaultdict(int)

    @property
    def enabled(self) -> bool:
        return self.cache.backend != "null"

    @property
    def backend(self) -> str:
        return self.cache.backend

    # -- raw bytes with isolation ------------------------------------------------------------------------------
    async def _get(self, kind: str, key: str) -> bytes | None:
        try:
            value = await self.cache.get(key)
        except CacheError as exc:
            logger.warning("cache.get_failed", kind=kind, error=str(exc))
            value = None
        if value is None:
            self._misses[kind] += 1
        else:
            self._hits[kind] += 1
        return value

    async def _set(self, kind: str, key: str, value: bytes, ttl: int) -> bool:
        try:
            return await self.cache.set(key, value, ttl)
        except CacheError as exc:
            logger.warning("cache.set_failed", kind=kind, error=str(exc))
            return False

    async def _forget(self, key: str) -> None:
        try:
            await self.cache.delete(key)
        except CacheError:
            pass

    def _demote(self, kind: str) -> None:
        """A stored value turned out unusable: count it as a miss, not a hit."""
        self._hits[kind] -= 1
        self._misses[kind] += 1

    # -- JSON ---------------------------------------------------------------------------------------------------
    async def get_json(self, kind: str, key: str) -> Any | None:
        raw = await self._get(kind, key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            self._demote(kind)
            await self._forget(key)
            return None

    async def set_json(self, kind: str, key: str, value: Any, ttl: int) -> bool:
        return await self._set(kind, key, json.dumps(value, separators=(",", ":")).encode(), ttl)

    # -- vectors (float32, little endian: what pgvector stores) ---------------------------------------------------
    async def get_vector(self, kind: str, key: str, dimension: int) -> list[float] | None:
        raw = await self._get(kind, key)
        if raw is None:
            return None
        if len(raw) != 4 * dimension:
            self._demote(kind)
            await self._forget(key)
            return None
        return list(struct.unpack(f"<{dimension}f", raw))

    async def set_vector(self, kind: str, key: str, vector: list[float], ttl: int) -> bool:
        return await self._set(kind, key, struct.pack(f"<{len(vector)}f", *vector), ttl)

    # -- corpus versions ----------------------------------------------------------------------------------------
    async def _token(self, tenant_id: str) -> str:
        key = self.keys.key(K.CORPUS, tenant_id)
        raw = await self._get(K.CORPUS, key)
        if raw is not None:
            return raw.decode("ascii", "replace")
        token = secrets.token_hex(8)
        await self._set(K.CORPUS, key, token.encode("ascii"), self.ttls.corpus_version)
        return token

    async def corpus_version(self, tenant_id: object) -> str:
        """Token naming the state of the corpus this tenant can search: its own documents plus the shared ones."""
        return f"{await self._token(str(tenant_id))}.{await self._token(GLOBAL_CORPUS)}"

    async def invalidate_corpus(self, tenant_id: object) -> None:
        """A document of ``tenant_id`` changed (or of everyone, for ``GLOBAL_CORPUS``): drop what depended on it.

        Replacing the token makes every key built before now unreachable even for a request that is in flight;
        the prefix delete then frees the memory. Verdicts and embeddings depend on text only, so they stay.
        """
        tenant = str(tenant_id)
        await self._set(
            K.CORPUS,
            self.keys.key(K.CORPUS, tenant),
            secrets.token_hex(8).encode("ascii"),
            self.ttls.corpus_version,
        )
        if tenant == GLOBAL_CORPUS:
            return  # the new token is enough; per-tenant entries become unreachable and then expire
        try:
            await self.cache.delete_prefix(self.keys.tenant_prefix(tenant, K.RETRIEVAL))
        except CacheError as exc:
            logger.warning("cache.purge_failed", error=str(exc))

    # -- observability ------------------------------------------------------------------------------------------
    def counters(self) -> dict[str, dict[str, int]]:
        kinds = set(self._hits) | set(self._misses)
        return {k: {"hit": self._hits[k], "miss": self._misses[k]} for k in sorted(kinds)}

    def stats(self) -> CacheStats:
        return self.cache.stats()

    async def aclose(self) -> None:
        await self.cache.aclose()
