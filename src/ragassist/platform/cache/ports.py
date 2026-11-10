"""Port of the cache platform: a bounded key/value store with a time to live on every entry (ADR 0015).

Values are ``bytes`` so every adapter (a process-local LRU, Redis) stores exactly the same thing and the caller owns
the encoding. The port is deliberately small: ``get``, ``set`` with a mandatory TTL, ``delete``, ``delete_prefix``,
and an atomic counter (``incr``) for the shared rate limiter. A backend failure is never raised to the caller of the
cache facade: a cache is an optimisation, so an unreachable store behaves like a miss.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class CacheError(Exception):
    """The backing store failed (connection lost, timeout). Adapters raise it; the facade turns it into a miss."""


@dataclass(frozen=True)
class CacheStats:
    """Counters since the process started. ``size`` is the number of live entries when the adapter knows it."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    rejected: int = 0
    errors: int = 0
    size: int = 0


@runtime_checkable
class Cache(Protocol):
    """A bounded store. Every key must come from ``CacheKeyBuilder`` so it carries the tenant."""

    @property
    def backend(self) -> str:
        """Adapter name used as a metrics label (``memory``, ``redis``, ``null``)."""
        ...

    async def get(self, key: str) -> bytes | None:
        """The stored value, or ``None`` on a miss or after the entry expired."""
        ...

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        """Store ``value`` for ``ttl_seconds`` (must be positive). ``False`` when it was refused (too large)."""
        ...

    async def delete(self, key: str) -> None: ...

    async def delete_prefix(self, prefix: str) -> int:
        """Remove every entry whose key starts with ``prefix``; returns how many were removed."""
        ...

    async def incr(self, key: str, ttl_seconds: int) -> int:
        """Atomically add one to a counter and return the new value; a new counter lives ``ttl_seconds``."""
        ...

    def stats(self) -> CacheStats: ...

    async def aclose(self) -> None: ...
