"""Process-local LRU cache with a TTL per entry: the default adapter (ADR 0015).

* Bounded twice: at most ``max_entries`` live entries (least recently used goes first) and no single value above
  ``max_value_bytes`` (a larger value is refused and counted, never stored).
* Every entry expires: ``set`` requires a positive TTL, and an expired entry is dropped when it is read or when the
  store is full.
* All methods run on the event loop thread and never ``await`` inside a critical section, so no lock is needed.
  ``delete_prefix`` scans the (bounded) table; that is fine for ten thousand entries and runs only when a tenant's
  documents change.

Consulted: ``collections.OrderedDict`` (``move_to_end`` / ``popitem(last=False)``) for the LRU order; the same
bounded-table approach already used by ``LoginThrottle`` in this repository.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable

from ragassist.platform.cache.ports import CacheStats


class InMemoryCache:
    backend = "memory"

    def __init__(
        self,
        *,
        max_entries: int,
        max_value_bytes: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries < 1 or max_value_bytes < 1:
            raise ValueError("max_entries and max_value_bytes must be positive")
        self._max_entries = max_entries
        self._max_value_bytes = max_value_bytes
        self._clock = clock
        self._items: OrderedDict[str, tuple[bytes, float]] = OrderedDict()
        self._hits = self._misses = self._evictions = self._expirations = self._rejected = 0

    async def get(self, key: str) -> bytes | None:
        entry = self._items.get(key)
        if entry is None:
            self._misses += 1
            return None
        value, expires_at = entry
        if expires_at <= self._clock():
            del self._items[key]
            self._expirations += 1
            self._misses += 1
            return None
        self._items.move_to_end(key)
        self._hits += 1
        return value

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            raise ValueError("every cache entry needs a positive TTL")
        if len(value) > self._max_value_bytes:
            self._rejected += 1
            return False
        if key in self._items:
            del self._items[key]
        elif len(self._items) >= self._max_entries:
            self._make_room()
        self._items[key] = (value, self._clock() + ttl_seconds)
        return True

    async def delete(self, key: str) -> None:
        self._items.pop(key, None)

    async def delete_prefix(self, prefix: str) -> int:
        doomed = [k for k in self._items if k.startswith(prefix)]
        for key in doomed:
            del self._items[key]
        return len(doomed)

    async def incr(self, key: str, ttl_seconds: int) -> int:
        now = self._clock()
        entry = self._items.get(key)
        if entry is not None and entry[1] > now:
            count = int(entry[0]) + 1
            self._items[key] = (str(count).encode(), entry[1])  # the window keeps its original expiry
            self._items.move_to_end(key)
            return count
        if entry is not None:
            del self._items[key]
        elif len(self._items) >= self._max_entries:
            self._make_room()
        self._items[key] = (b"1", now + ttl_seconds)
        return 1

    def _make_room(self) -> None:
        """Drop expired entries first; if the table is still full, drop the least recently used one."""
        now = self._clock()
        expired = [k for k, (_, exp) in self._items.items() if exp <= now]
        for key in expired:
            del self._items[key]
        self._expirations += len(expired)
        while len(self._items) >= self._max_entries:
            self._items.popitem(last=False)
            self._evictions += 1

    def stats(self) -> CacheStats:
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            evictions=self._evictions,
            expirations=self._expirations,
            rejected=self._rejected,
            size=len(self._items),
        )

    async def aclose(self) -> None:
        self._items.clear()
