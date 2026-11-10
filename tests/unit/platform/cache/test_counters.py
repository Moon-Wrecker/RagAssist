"""Shared counters on the cache backend (ADR 0015): the Redis side of the sign-in throttle and rate limiter."""

from __future__ import annotations

import pytest
from fakes.clock import FakeClock
from support.settings import make_settings

from ragassist.platform.cache import build_cache_service, get_shared_counters
from ragassist.platform.cache.adapters.memory_adapter import InMemoryCache
from ragassist.platform.cache.counters import CacheCounters
from ragassist.platform.cache.ports import CacheError
from ragassist.shared.config import settings as settings_module


def counters(clock: FakeClock, cache: InMemoryCache | None = None, **kw: float) -> CacheCounters:
    cache = cache or InMemoryCache(max_entries=100, max_value_bytes=4096, clock=clock.now)
    service = build_cache_service(make_settings(), cache)
    return CacheCounters(service, clock=clock.now, **kw)


class FailingCache(InMemoryCache):
    def __init__(self, clock: FakeClock) -> None:
        super().__init__(max_entries=10, max_value_bytes=1024, clock=clock.now)
        self.calls = 0

    async def incr(self, key: str, ttl_seconds: int) -> int:
        self.calls += 1
        raise CacheError("ConnectionError")

    async def get(self, key: str) -> bytes | None:
        self.calls += 1
        raise CacheError("ConnectionError")

    async def delete(self, key: str) -> None:
        self.calls += 1
        raise CacheError("ConnectionError")


class TestCounting:
    async def test_incr_counts_inside_one_window_and_peek_reads_it(self) -> None:
        clock = FakeClock()
        c = counters(clock)
        assert [await c.incr("loginfail", "acct", 60) for _ in range(3)] == [1, 2, 3]
        assert await c.peek("loginfail", "acct") == 3

    async def test_a_new_window_starts_when_the_old_one_ends(self) -> None:
        clock = FakeClock()
        c = counters(clock)
        await c.incr("ratelimit", "ip", 60)
        await c.incr("ratelimit", "ip", 60)
        clock.advance(61)
        assert await c.peek("ratelimit", "ip") == 0
        assert await c.incr("ratelimit", "ip", 60) == 1

    async def test_names_and_identifiers_are_separate_counters(self) -> None:
        c = counters(FakeClock())
        await c.incr("loginip", "x", 60)
        assert await c.peek("loginfail", "x") == 0
        assert await c.peek("loginip", "y") == 0

    async def test_reset_forgets_the_counter(self) -> None:
        c = counters(FakeClock())
        await c.incr("loginfail", "x", 60)
        await c.reset("loginfail", "x")
        assert await c.peek("loginfail", "x") == 0

    async def test_keys_hold_neither_the_identifier_nor_a_tenant_free_plain_text(self) -> None:
        clock = FakeClock()
        cache = InMemoryCache(max_entries=10, max_value_bytes=1024, clock=clock.now)
        c = counters(clock, cache)
        await c.incr("loginfail", "person@example.com", 60)
        keys = list(cache._items)
        assert keys and all("person" not in k and "example" not in k for k in keys)


class TestBackendFailure:
    async def test_every_operation_answers_none_or_nothing_when_the_store_is_down(self) -> None:
        clock = FakeClock()
        c = counters(clock, FailingCache(clock))
        assert await c.incr("ratelimit", "ip", 60) is None
        clock.advance(10)
        assert await c.peek("ratelimit", "ip") is None
        clock.advance(10)
        await c.reset("ratelimit", "ip")  # does not raise

    async def test_after_a_failure_the_breaker_skips_the_store_for_a_while(self) -> None:
        clock = FakeClock()
        cache = FailingCache(clock)
        c = counters(clock, cache, breaker_seconds=5.0)
        assert await c.incr("ratelimit", "ip", 60) is None
        assert cache.calls == 1
        for _ in range(20):
            assert await c.incr("ratelimit", "ip", 60) is None
        assert cache.calls == 1  # not one timeout per request
        clock.advance(6)
        await c.incr("ratelimit", "ip", 60)
        assert cache.calls == 2


class TestFactory:
    @pytest.fixture(autouse=True)
    def _settings(self, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
        yield monkeypatch

    def test_none_with_the_memory_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings_module, "_settings", make_settings(CACHE_BACKEND="memory"))
        assert get_shared_counters() is None

    def test_none_when_the_cache_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            settings_module,
            "_settings",
            make_settings(
                CACHE_ENABLED=False,
                CACHE_BACKEND="redis",
                CACHE_REDIS_URL="redis://cache.internal:6379/0",
            ),
        )
        assert get_shared_counters() is None

    def test_present_with_the_redis_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            settings_module,
            "_settings",
            make_settings(CACHE_BACKEND="redis", CACHE_REDIS_URL="redis://cache.internal:6379/0"),
        )
        assert isinstance(get_shared_counters(), CacheCounters)
