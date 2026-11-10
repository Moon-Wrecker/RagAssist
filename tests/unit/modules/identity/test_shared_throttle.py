"""The sign-in throttle and the rate limiter on counters shared between replicas (ADR 0015).

Two throttles (two API replicas) that share one counter store must behave as one; when the store is down each falls
back to its own exact in-process logic.
"""

from __future__ import annotations

import httpx
import pytest
from fakes.clock import FakeClock
from fastapi import FastAPI
from support.settings import make_settings

from ragassist.modules.identity.application import LoginThrottle
from ragassist.modules.identity.domain import RateLimitedError
from ragassist.platform.cache import build_cache_service
from ragassist.platform.cache.adapters.memory_adapter import InMemoryCache
from ragassist.platform.cache.counters import CacheCounters
from ragassist.shared.security.rate_limiter import RateLimitMiddleware, SlidingWindowRateLimiter


def shared_store(clock: FakeClock) -> CacheCounters:
    cache = InMemoryCache(max_entries=1000, max_value_bytes=4096, clock=clock.now)
    return CacheCounters(build_cache_service(make_settings(), cache), clock=clock.now)


class DownCounters:
    """A shared store that is unreachable."""

    async def incr(self, name: str, ident: str, window_seconds: int) -> int | None:
        return None

    async def peek(self, name: str, ident: str) -> int | None:
        return None

    async def reset(self, name: str, ident: str) -> None:
        return None


def replica(shared, clock: FakeClock, *, failures: int = 3, per_ip: int = 10) -> LoginThrottle:  # type: ignore[no-untyped-def]
    return LoginThrottle(
        max_failures=failures, max_per_ip=per_ip, window_seconds=60, clock=clock.now, shared=shared
    )


class TestSharedLoginThrottle:
    async def test_failures_on_two_replicas_lock_the_account_together(self) -> None:
        clock = FakeClock()
        store = shared_store(clock)
        a, b = replica(store, clock, failures=3), replica(store, clock, failures=3)
        for node in (a, b, a):
            await node.acheck("1.1.1.1", "acme", "p@x.com")
            await node.arecord_failure("acme", "p@x.com")
        for node in (a, b):
            with pytest.raises(RateLimitedError):
                await node.acheck("9.9.9.9", "acme", "p@x.com")

    async def test_attempts_from_one_address_are_counted_across_replicas(self) -> None:
        clock = FakeClock()
        store = shared_store(clock)
        a, b = replica(store, clock, per_ip=4), replica(store, clock, per_ip=4)
        for node in (a, b, a, b):
            await node.acheck("1.1.1.1", "acme", "someone@x.com")
        with pytest.raises(RateLimitedError):
            await a.acheck("1.1.1.1", "acme", "other@x.com")

    async def test_a_success_clears_the_count_on_every_replica(self) -> None:
        clock = FakeClock()
        store = shared_store(clock)
        a, b = replica(store, clock, failures=2), replica(store, clock, failures=2)
        await a.arecord_failure("acme", "p@x.com")
        await b.arecord_success("acme", "p@x.com")
        await a.arecord_failure("acme", "p@x.com")
        await a.acheck("1.1.1.1", "acme", "p@x.com")  # one failure since the success: allowed

    async def test_the_window_ends(self) -> None:
        clock = FakeClock()
        store = shared_store(clock)
        node = replica(store, clock, failures=1)
        await node.arecord_failure("acme", "p@x.com")
        with pytest.raises(RateLimitedError):
            await node.acheck("1.1.1.1", "acme", "p@x.com")
        clock.advance(61)
        await node.acheck("1.1.1.1", "acme", "p@x.com")

    async def test_another_account_is_unaffected(self) -> None:
        clock = FakeClock()
        node = replica(shared_store(clock), clock, failures=1)
        await node.arecord_failure("acme", "p@x.com")
        await node.acheck("1.1.1.1", "acme", "q@x.com")

    async def test_with_the_store_down_the_in_process_logic_still_locks(self) -> None:
        clock = FakeClock()
        node = replica(DownCounters(), clock, failures=2)
        for _ in range(2):
            await node.acheck("1.1.1.1", "acme", "p@x.com")
            await node.arecord_failure("acme", "p@x.com")
        with pytest.raises(RateLimitedError):
            await node.acheck("1.1.1.1", "acme", "p@x.com")

    async def test_without_shared_counters_the_async_methods_match_the_sync_ones(self) -> None:
        clock = FakeClock()
        node = replica(None, clock, failures=1)
        await node.arecord_failure("acme", "p@x.com")
        with pytest.raises(RateLimitedError):
            await node.acheck("1.1.1.1", "acme", "p@x.com")
        await node.arecord_success("acme", "p@x.com")
        await node.acheck("1.1.1.1", "acme", "p@x.com")


def limited_app(limiter: SlidingWindowRateLimiter, shared) -> FastAPI:  # type: ignore[no-untyped-def]
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limiter=limiter, shared=shared, exempt_paths=set())

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "1"}

    return app


async def hit(app: FastAPI) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.get("/ping")


class TestSharedRateLimiter:
    async def test_two_replicas_share_one_allowance(self) -> None:
        clock = FakeClock()
        store = shared_store(clock)
        a = limited_app(SlidingWindowRateLimiter(limit=3, window_seconds=60), store)
        b = limited_app(SlidingWindowRateLimiter(limit=3, window_seconds=60), store)
        statuses = [(await hit(app)).status_code for app in (a, b, a, b, a)]
        assert statuses == [200, 200, 200, 429, 429]

    async def test_the_429_carries_retry_after_and_the_headers(self) -> None:
        clock = FakeClock()
        app = limited_app(SlidingWindowRateLimiter(limit=1, window_seconds=60), shared_store(clock))
        await hit(app)
        blocked = await hit(app)
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
        assert blocked.headers["x-ratelimit-remaining"] == "0"

    async def test_remaining_counts_down_from_the_shared_value(self) -> None:
        app = limited_app(
            SlidingWindowRateLimiter(limit=5, window_seconds=60), shared_store(FakeClock())
        )
        remaining = [(await hit(app)).headers["x-ratelimit-remaining"] for _ in range(3)]
        assert remaining == ["4", "3", "2"]

    async def test_with_the_store_down_each_replica_limits_on_its_own(self) -> None:
        app = limited_app(SlidingWindowRateLimiter(limit=2, window_seconds=60), DownCounters())
        assert [(await hit(app)).status_code for _ in range(3)] == [200, 200, 429]

    async def test_without_shared_counters_nothing_changes(self) -> None:
        app = limited_app(SlidingWindowRateLimiter(limit=2, window_seconds=60), None)
        assert [(await hit(app)).status_code for _ in range(3)] == [200, 200, 429]
