"""In-memory LRU+TTL adapter: TTL, size bounds, eviction order, prefix delete, counters (ADR 0015)."""

from __future__ import annotations

import pytest
from fakes.clock import FakeClock

from ragassist.platform.cache.adapters.memory_adapter import InMemoryCache
from ragassist.platform.cache.adapters.null_adapter import NullCache
from ragassist.platform.cache.ports import Cache


def make(clock: FakeClock | None = None, **kw: int) -> InMemoryCache:
    clock = clock or FakeClock()
    return InMemoryCache(
        max_entries=kw.get("max_entries", 3),
        max_value_bytes=kw.get("max_value_bytes", 16),
        clock=clock.now,
    )


class TestContract:
    def test_adapters_satisfy_the_port(self) -> None:
        assert isinstance(make(), Cache)
        assert isinstance(NullCache(), Cache)

    async def test_set_then_get(self) -> None:
        cache = make()
        assert await cache.set("k", b"v", 10) is True
        assert await cache.get("k") == b"v"

    async def test_a_miss_is_none(self) -> None:
        assert await make().get("absent") is None

    async def test_every_entry_needs_a_positive_ttl(self) -> None:
        with pytest.raises(ValueError):
            await make().set("k", b"v", 0)


class TestTtl:
    async def test_entry_expires(self) -> None:
        clock = FakeClock()
        cache = make(clock)
        await cache.set("k", b"v", 10)
        clock.advance(9)
        assert await cache.get("k") == b"v"
        clock.advance(2)
        assert await cache.get("k") is None
        assert cache.stats().expirations == 1

    async def test_overwrite_restarts_the_clock(self) -> None:
        clock = FakeClock()
        cache = make(clock)
        await cache.set("k", b"1", 10)
        clock.advance(8)
        await cache.set("k", b"2", 10)
        clock.advance(8)
        assert await cache.get("k") == b"2"


class TestBounds:
    async def test_least_recently_used_goes_first(self) -> None:
        cache = make()
        for key in ("a", "b", "c"):
            await cache.set(key, b"x", 100)
        await cache.get("a")  # a is now the freshest
        await cache.set("d", b"x", 100)
        assert await cache.get("b") is None
        assert await cache.get("a") == b"x"
        assert cache.stats().evictions == 1
        assert cache.stats().size == 3

    async def test_expired_entries_are_dropped_before_live_ones_are_evicted(self) -> None:
        clock = FakeClock()
        cache = make(clock)
        await cache.set("old", b"x", 1)
        await cache.set("b", b"x", 100)
        await cache.set("c", b"x", 100)
        clock.advance(5)
        await cache.set("d", b"x", 100)
        assert cache.stats().evictions == 0
        assert await cache.get("b") == b"x"

    async def test_size_never_exceeds_the_bound(self) -> None:
        cache = make(max_entries=5)
        for i in range(100):
            await cache.set(f"k{i}", b"x", 100)
        assert cache.stats().size == 5

    async def test_an_oversized_value_is_refused_and_counted(self) -> None:
        cache = make(max_value_bytes=4)
        assert await cache.set("k", b"12345", 10) is False
        assert await cache.get("k") is None
        assert cache.stats().rejected == 1

    def test_bounds_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            InMemoryCache(max_entries=0, max_value_bytes=1)


class TestPrefixAndCounters:
    async def test_delete_prefix_removes_only_matching_keys(self) -> None:
        cache = make(max_entries=10)
        for key in ("t1:a", "t1:b", "t2:a"):
            await cache.set(key, b"x", 100)
        assert await cache.delete_prefix("t1:") == 2
        assert await cache.get("t2:a") == b"x"
        assert await cache.get("t1:a") is None

    async def test_delete_one(self) -> None:
        cache = make()
        await cache.set("k", b"x", 100)
        await cache.delete("k")
        assert await cache.get("k") is None

    async def test_hits_and_misses_are_counted(self) -> None:
        cache = make()
        await cache.set("k", b"x", 100)
        await cache.get("k")
        await cache.get("k")
        await cache.get("nope")
        stats = cache.stats()
        assert (stats.hits, stats.misses) == (2, 1)

    async def test_counter_counts_inside_one_window_and_restarts_after_it(self) -> None:
        clock = FakeClock()
        cache = make(clock)
        assert [await cache.incr("c", 10) for _ in range(3)] == [1, 2, 3]
        clock.advance(5)
        assert await cache.incr("c", 10) == 4  # the window keeps its original expiry
        clock.advance(6)
        assert await cache.incr("c", 10) == 1

    async def test_null_cache_never_stores(self) -> None:
        cache = NullCache()
        assert await cache.set("k", b"x", 10) is False
        assert await cache.get("k") is None
