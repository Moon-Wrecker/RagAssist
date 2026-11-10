"""Shared counters on the cache backend (ADR 0015): the Redis side of ``ragassist.shared.counters.SharedCounters``.

Only used when ``CACHE_BACKEND=redis``: with the in-memory backend a "shared" counter would still be per process, so
the callers keep their own exact sliding-window logic and this adapter is not built. Keys come from
``CacheKeyBuilder.shared_counter_key`` (keyed hash, so no address or e-mail is stored).

A failure opens a short breaker (``BREAKER_SECONDS``): during it every call answers ``None`` immediately, so a slow or
hung Redis costs one timeout, not one per request, and callers use their in-process counters meanwhile.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import structlog

from ragassist.platform.cache.ports import CacheError
from ragassist.platform.cache.service import CacheService

logger = structlog.get_logger(__name__)

BREAKER_SECONDS = 5.0


class CacheCounters:
    def __init__(
        self,
        service: CacheService,
        *,
        clock: Callable[[], float] = time.monotonic,
        breaker_seconds: float = BREAKER_SECONDS,
    ) -> None:
        self._service = service
        self._clock = clock
        self._breaker = breaker_seconds
        self._open_until = 0.0

    def _key(self, name: str, ident: str) -> str:
        return self._service.keys.shared_counter_key(name, ident)

    def _down(self) -> bool:
        return self._clock() < self._open_until

    def _trip(self, op: str, exc: Exception) -> None:
        self._open_until = self._clock() + self._breaker
        logger.warning("cache.counters_unavailable", op=op, error=str(exc))

    async def incr(self, name: str, ident: str, window_seconds: int) -> int | None:
        if self._down():
            return None
        try:
            return await self._service.cache.incr(self._key(name, ident), max(1, int(window_seconds)))
        except CacheError as exc:
            self._trip("incr", exc)
            return None

    async def peek(self, name: str, ident: str) -> int | None:
        if self._down():
            return None
        try:
            raw = await self._service.cache.get(self._key(name, ident))
        except CacheError as exc:
            self._trip("peek", exc)
            return None
        try:
            return int(raw) if raw is not None else 0
        except ValueError:
            return 0

    async def reset(self, name: str, ident: str) -> None:
        if self._down():
            return
        try:
            await self._service.cache.delete(self._key(name, ident))
        except CacheError as exc:
            self._trip("reset", exc)
