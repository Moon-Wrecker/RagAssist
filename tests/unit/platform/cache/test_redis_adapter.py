"""Redis adapter against a fake client (always) and a real server (only when one is configured), ADR 0015."""

from __future__ import annotations

import fnmatch
import os
import secrets
from collections.abc import AsyncIterator
from typing import Any

import pytest

from ragassist.platform.cache.adapters.redis_adapter import RedisCache, escape_glob
from ragassist.platform.cache.ports import Cache, CacheError


class _Pipeline:
    def __init__(self, client: FakeRedis) -> None:
        self._client = client
        self._ops: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def __aenter__(self) -> _Pipeline:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def set(self, *args: Any, **kwargs: Any) -> None:
        self._ops.append(("set", args, kwargs))

    def incr(self, *args: Any, **kwargs: Any) -> None:
        self._ops.append(("incr", args, kwargs))

    async def execute(self) -> list[Any]:
        return [await getattr(self._client, name)(*a, **k) for name, a, k in self._ops]


class FakeRedis:
    """Just enough of ``redis.asyncio.Redis`` for the adapter: bytes in, bytes out, expiry recorded."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.expiry: dict[str, int] = {}
        self.fail = False
        self.closed = False

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("boom: host unreachable")

    async def get(self, key: str) -> bytes | None:
        self._check()
        return self.data.get(key)

    async def set(
        self, key: str, value: Any, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        self._check()
        if nx and key in self.data:
            return None
        self.data[key] = value if isinstance(value, bytes) else str(value).encode()
        if ex is not None:
            self.expiry[key] = ex
        return True

    async def incr(self, key: str) -> int:
        self._check()
        self.data[key] = str(int(self.data.get(key, b"0")) + 1).encode()
        return int(self.data[key])

    async def unlink(self, *keys: str) -> int:
        self._check()
        return sum(1 for k in keys if self.data.pop(k, None) is not None)

    async def scan_iter(
        self, match: str | None = None, count: int | None = None
    ) -> AsyncIterator[str]:
        self._check()
        for key in list(self.data):
            if match is None or fnmatch.fnmatchcase(key, match.replace("\\", "")):
                yield key

    def pipeline(self, transaction: bool = True) -> _Pipeline:
        return _Pipeline(self)

    async def aclose(self) -> None:
        self.closed = True


def adapter(
    client: FakeRedis | None = None, max_value_bytes: int = 64
) -> tuple[RedisCache, FakeRedis]:
    client = client or FakeRedis()
    return RedisCache(url="", max_value_bytes=max_value_bytes, client=client), client


class TestWithAFakeClient:
    def test_satisfies_the_port(self) -> None:
        assert isinstance(adapter()[0], Cache)

    async def test_set_get_and_the_expiry_is_always_sent(self) -> None:
        cache, client = adapter()
        assert await cache.set("k", b"v", 30) is True
        assert await cache.get("k") == b"v"
        assert client.expiry["k"] == 30

    async def test_miss_and_counters(self) -> None:
        cache, _ = adapter()
        await cache.set("k", b"v", 30)
        await cache.get("k")
        await cache.get("nope")
        assert (cache.stats().hits, cache.stats().misses) == (1, 1)

    async def test_oversized_value_is_refused(self) -> None:
        cache, client = adapter(max_value_bytes=3)
        assert await cache.set("k", b"1234", 30) is False
        assert "k" not in client.data
        assert cache.stats().rejected == 1

    async def test_ttl_is_mandatory(self) -> None:
        cache, _ = adapter()
        with pytest.raises(ValueError):
            await cache.set("k", b"v", 0)

    async def test_prefix_delete_is_literal_and_scoped(self) -> None:
        cache, client = adapter()
        for key in ("p:t1:a", "p:t1:b", "p:t2:a"):
            await cache.set(key, b"x", 30)
        assert await cache.delete_prefix("p:t1:") == 2
        assert set(client.data) == {"p:t2:a"}

    async def test_counter_is_atomic_window_counter(self) -> None:
        cache, client = adapter()
        assert [await cache.incr("c", 60) for _ in range(3)] == [1, 2, 3]
        assert client.expiry["c"] == 60

    async def test_client_failures_become_cache_errors_without_leaking_details(self) -> None:
        cache, client = adapter()
        client.fail = True
        for call in (
            cache.get("k"),
            cache.set("k", b"v", 5),
            cache.delete("k"),
            cache.delete_prefix("p"),
            cache.incr("c", 5),
        ):
            with pytest.raises(CacheError) as info:
                await call
            assert "unreachable" not in str(info.value)  # the class name only, never host details
        assert cache.stats().errors == 5

    async def test_close_closes_the_client(self) -> None:
        cache, client = adapter()
        await cache.aclose()
        assert client.closed

    def test_glob_characters_in_a_prefix_are_escaped(self) -> None:
        assert escape_glob("a*b?c[d]e\\f") == "a\\*b\\?c\\[d\\]e\\\\f"


REAL_URL = os.environ.get("RAGASSIST_TEST_REDIS_URL", "")


@pytest.mark.skipif(
    not REAL_URL, reason="set RAGASSIST_TEST_REDIS_URL to run against a real Redis server"
)
class TestAgainstARealServer:
    """Opt-in: a disposable server, e.g. ``docker run --rm -p 127.0.0.1:<port>:6379 redis:8.2.11-alpine``."""

    @pytest.fixture
    async def cache(self) -> AsyncIterator[RedisCache]:
        pytest.importorskip("redis")
        password = os.environ.get("RAGASSIST_TEST_REDIS_PASSWORD", "")
        cache = RedisCache(url=REAL_URL, password=password, max_value_bytes=1024)
        yield cache
        await cache.aclose()

    @pytest.fixture
    def prefix(self) -> str:
        return f"test-{secrets.token_hex(6)}:"

    @pytest.mark.network
    async def test_round_trip_ttl_prefix_and_counter(self, cache: RedisCache, prefix: str) -> None:
        assert await cache.set(prefix + "a", b"one", 30)
        assert await cache.get(prefix + "a") == b"one"
        assert await cache.set(prefix + "b", b"two", 30)
        assert await cache.delete_prefix(prefix) == 2
        assert await cache.get(prefix + "a") is None
        assert [await cache.incr(prefix + "c", 30) for _ in range(3)] == [1, 2, 3]
        await cache.delete(prefix + "c")
