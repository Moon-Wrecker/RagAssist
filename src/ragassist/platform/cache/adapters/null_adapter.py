"""A cache that stores nothing: what ``CACHE_ENABLED=false`` wires, so callers never branch on "is there a cache"."""

from __future__ import annotations

from ragassist.platform.cache.ports import CacheStats


class NullCache:
    backend = "null"

    async def get(self, key: str) -> bytes | None:
        return None

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        return False

    async def delete(self, key: str) -> None:
        return None

    async def delete_prefix(self, prefix: str) -> int:
        return 0

    async def incr(self, key: str, ttl_seconds: int) -> int:
        return 1

    def stats(self) -> CacheStats:
        return CacheStats()

    async def aclose(self) -> None:
        return None
