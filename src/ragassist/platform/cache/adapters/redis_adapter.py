"""Redis cache adapter (optional, ADR 0015): one store shared by every API replica and the worker.

Consulted:
* redis-py (``redis`` on PyPI, MIT, maintained by Redis Inc., about 200 million downloads a month, pinned to an exact
  version in ``pyproject.toml``): its ``redis.asyncio`` client, ``Redis.from_url``, ``SET ... EX``, ``scan_iter`` and
  ``UNLINK`` https://redis.readthedocs.io/en/latest/ and https://redis.io/docs/latest/commands/scan/.
* Redis ``SCAN`` is cursor based and non-blocking, unlike ``KEYS``, so a prefix purge never stalls the server.
* ``INCR`` on a key created by ``SET key 0 EX ttl NX`` inside one ``MULTI`` gives an atomic fixed-window counter on
  every Redis version (``EXPIRE ... NX`` needs 7.0).

Rules kept here: the password comes from ``CACHE_REDIS_PASSWORD`` (never the URL, never code); every ``set`` carries an
expiry; one value never exceeds ``max_value_bytes``; any client failure becomes ``CacheError`` so the facade can treat
it as a miss. Values can contain tenant text (retrieved passages), so the Redis instance must be private to the
deployment (compose network or a firewalled host, a password, and ``rediss://`` across hosts).
"""

from __future__ import annotations

from typing import Any

import structlog

from ragassist.platform.cache.ports import CacheError, CacheStats

logger = structlog.get_logger(__name__)

_SCAN_COUNT = 500
_GLOB_SPECIALS = str.maketrans({c: "\\" + c for c in "\\*?[]"})


def escape_glob(text: str) -> str:
    """Escape the characters ``SCAN MATCH`` treats as pattern syntax so a prefix matches literally."""
    return text.translate(_GLOB_SPECIALS)


class RedisCache:
    backend = "redis"

    def __init__(
        self,
        *,
        url: str,
        password: str = "",
        timeout_seconds: float = 1.0,
        max_value_bytes: int,
        client: Any | None = None,
    ) -> None:
        if client is None:
            import redis.asyncio as redis

            client = redis.Redis.from_url(
                url,
                password=password or None,
                socket_timeout=timeout_seconds,
                socket_connect_timeout=timeout_seconds,
                decode_responses=False,
            )
        self._client = client
        self._max_value_bytes = max_value_bytes
        self._hits = self._misses = self._rejected = self._errors = 0

    @staticmethod
    def _error(exc: Exception) -> CacheError:
        return CacheError(type(exc).__name__)

    async def get(self, key: str) -> bytes | None:
        try:
            value = await self._client.get(key)
        except Exception as exc:  # noqa: BLE001 - any client failure is a backend failure
            self._errors += 1
            raise self._error(exc) from exc
        if value is None:
            self._misses += 1
            return None
        self._hits += 1
        return bytes(value)

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            raise ValueError("every cache entry needs a positive TTL")
        if len(value) > self._max_value_bytes:
            self._rejected += 1
            return False
        try:
            await self._client.set(key, value, ex=ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            self._errors += 1
            raise self._error(exc) from exc
        return True

    async def delete(self, key: str) -> None:
        try:
            await self._client.unlink(key)
        except Exception as exc:  # noqa: BLE001
            self._errors += 1
            raise self._error(exc) from exc

    async def delete_prefix(self, prefix: str) -> int:
        removed = 0
        try:
            batch: list[bytes] = []
            async for key in self._client.scan_iter(match=escape_glob(prefix) + "*", count=_SCAN_COUNT):
                batch.append(key)
                if len(batch) >= _SCAN_COUNT:
                    removed += int(await self._client.unlink(*batch))
                    batch = []
            if batch:
                removed += int(await self._client.unlink(*batch))
        except Exception as exc:  # noqa: BLE001
            self._errors += 1
            raise self._error(exc) from exc
        return removed

    async def incr(self, key: str, ttl_seconds: int) -> int:
        if ttl_seconds <= 0:
            raise ValueError("every counter needs a positive TTL")
        try:
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.set(key, 0, ex=ttl_seconds, nx=True)
                pipe.incr(key)
                results = await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            self._errors += 1
            raise self._error(exc) from exc
        return int(results[-1])

    def stats(self) -> CacheStats:
        return CacheStats(
            hits=self._hits, misses=self._misses, rejected=self._rejected, errors=self._errors
        )

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.redis_close_failed", error=type(exc).__name__)
