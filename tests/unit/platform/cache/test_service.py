"""Cache facade: codecs, failure isolation, corpus versions and settings wiring (ADR 0015)."""

from __future__ import annotations

import pytest
from fakes.clock import FakeClock
from pydantic import ValidationError
from support.settings import make_settings

from ragassist.platform.cache import (
    CacheService,
    build_cache,
    build_cache_service,
    get_cache_service,
    shutdown_cache,
)
from ragassist.platform.cache import keys as kinds
from ragassist.platform.cache.adapters.memory_adapter import InMemoryCache
from ragassist.platform.cache.adapters.null_adapter import NullCache
from ragassist.platform.cache.ports import CacheError, CacheStats

TENANT_A = "a0000000-0000-0000-0000-00000000000a"
TENANT_B = "b0000000-0000-0000-0000-00000000000b"


def service(clock: FakeClock | None = None, **settings: object) -> CacheService:
    clock = clock or FakeClock()
    cfg = make_settings(**settings)
    cache = InMemoryCache(max_entries=100, max_value_bytes=4096, clock=clock.now)
    return build_cache_service(cfg, cache)


class BrokenCache(NullCache):
    backend = "redis"

    async def get(self, key: str) -> bytes | None:
        raise CacheError("ConnectionError")

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        raise CacheError("ConnectionError")

    async def delete_prefix(self, prefix: str) -> int:
        raise CacheError("ConnectionError")

    def stats(self) -> CacheStats:
        return CacheStats()


class TestCodecs:
    async def test_json_round_trip(self) -> None:
        svc = service()
        key = svc.keys.key(kinds.DECISION, TENANT_A, role="customer", text="q")
        assert await svc.set_json(kinds.DECISION, key, {"is_safe": True, "n": [1, 2]}, 30)
        assert await svc.get_json(kinds.DECISION, key) == {"is_safe": True, "n": [1, 2]}

    async def test_vector_round_trip_is_float32(self) -> None:
        svc = service()
        key = svc.keys.key(kinds.EMBEDDING_QUERY, TENANT_A, text="q", context=("p", "m"))
        await svc.set_vector(kinds.EMBEDDING_QUERY, key, [0.5, -1.25, 3.0], 30)
        assert await svc.get_vector(kinds.EMBEDDING_QUERY, key, 3) == [0.5, -1.25, 3.0]

    async def test_a_vector_of_the_wrong_dimension_is_a_miss_and_is_dropped(self) -> None:
        svc = service()
        key = svc.keys.key(kinds.EMBEDDING_QUERY, TENANT_A, text="q")
        await svc.set_vector(kinds.EMBEDDING_QUERY, key, [1.0, 2.0], 30)
        assert await svc.get_vector(kinds.EMBEDDING_QUERY, key, 3) is None
        assert await svc.cache.get(key) is None
        assert svc.counters()[kinds.EMBEDDING_QUERY] == {"hit": 0, "miss": 1}

    async def test_a_corrupt_json_value_is_a_miss_and_is_dropped(self) -> None:
        svc = service()
        key = svc.keys.key(kinds.DECISION, TENANT_A, text="q")
        await svc.cache.set(key, b"not json{", 30)
        assert await svc.get_json(kinds.DECISION, key) is None
        assert await svc.cache.get(key) is None

    async def test_counters_are_kept_per_kind(self) -> None:
        svc = service()
        key = svc.keys.key(kinds.DECISION, TENANT_A, text="q")
        await svc.get_json(kinds.DECISION, key)
        await svc.set_json(kinds.DECISION, key, 1, 30)
        await svc.get_json(kinds.DECISION, key)
        assert svc.counters() == {kinds.DECISION: {"hit": 1, "miss": 1}}


class TestFailureIsolation:
    async def test_a_dead_backend_behaves_like_a_miss(self) -> None:
        svc = build_cache_service(make_settings(), BrokenCache())
        key = svc.keys.key(kinds.DECISION, TENANT_A, text="q")
        assert await svc.get_json(kinds.DECISION, key) is None
        assert await svc.set_json(kinds.DECISION, key, {"a": 1}, 30) is False
        await svc.invalidate_corpus(TENANT_A)  # must not raise
        assert isinstance(await svc.corpus_version(TENANT_A), str)

    async def test_disabled_cache_is_a_null_adapter(self) -> None:
        cfg = make_settings(CACHE_ENABLED=False)
        assert isinstance(build_cache(cfg), NullCache)
        assert build_cache_service(cfg).enabled is False


class TestCorpusVersion:
    async def test_version_is_stable_until_the_corpus_changes(self) -> None:
        svc = service()
        first = await svc.corpus_version(TENANT_A)
        assert await svc.corpus_version(TENANT_A) == first
        await svc.invalidate_corpus(TENANT_A)
        assert await svc.corpus_version(TENANT_A) != first

    async def test_changing_one_tenant_does_not_change_another(self) -> None:
        svc = service()
        b_before = await svc.corpus_version(TENANT_B)
        await svc.invalidate_corpus(TENANT_A)
        assert await svc.corpus_version(TENANT_B) == b_before

    async def test_a_shared_knowledge_change_changes_every_tenants_version(self) -> None:
        svc = service()
        a, b = await svc.corpus_version(TENANT_A), await svc.corpus_version(TENANT_B)
        await svc.invalidate_corpus("global")
        assert await svc.corpus_version(TENANT_A) != a
        assert await svc.corpus_version(TENANT_B) != b

    async def test_an_evicted_version_never_revives_old_entries(self) -> None:
        clock = FakeClock()
        svc = service(clock)
        first = await svc.corpus_version(TENANT_A)
        clock.advance(svc.ttls.corpus_version + 1)  # the token expires
        assert await svc.corpus_version(TENANT_A) != first

    async def test_invalidation_purges_that_tenants_retrieval_entries_only(self) -> None:
        svc = service()
        mine = svc.keys.key(kinds.RETRIEVAL, TENANT_A, role="agent", text="q")
        theirs = svc.keys.key(kinds.RETRIEVAL, TENANT_B, role="agent", text="q")
        verdict = svc.keys.key(kinds.DECISION, TENANT_A, role="agent", text="q")
        for key in (mine, theirs, verdict):
            await svc.set_json("x", key, {"v": 1}, 60)
        await svc.invalidate_corpus(TENANT_A)
        assert await svc.cache.get(mine) is None
        assert await svc.cache.get(theirs) is not None
        assert await svc.cache.get(verdict) is not None  # verdicts depend on text only


class TestSettings:
    def test_redis_needs_a_url(self) -> None:
        with pytest.raises(ValidationError):
            make_settings(CACHE_BACKEND="redis", CACHE_REDIS_URL="")

    def test_the_url_must_not_carry_credentials(self) -> None:
        with pytest.raises(ValidationError):
            make_settings(
                CACHE_BACKEND="redis", CACHE_REDIS_URL="redis://user:pw@cache.internal:6379/0"
            )

    def test_a_credential_free_url_is_accepted_and_the_password_is_masked(self) -> None:
        cfg = make_settings(
            CACHE_BACKEND="redis",
            CACHE_REDIS_URL="redis://cache.internal:6379/0",
            CACHE_REDIS_PASSWORD="throwaway-password-for-this-test",
        )
        assert "throwaway-password" not in repr(cfg)
        assert "throwaway-password" not in cfg.model_dump_json()

    def test_a_disabled_cache_needs_no_redis_url(self) -> None:
        assert make_settings(CACHE_ENABLED=False, CACHE_BACKEND="redis").CACHE_REDIS_URL == ""

    def test_ttls_and_bounds_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            make_settings(CACHE_RETRIEVAL_TTL_SECONDS=0)
        with pytest.raises(ValidationError):
            make_settings(CACHE_MAX_ENTRIES=0)

    async def test_the_process_wide_service_follows_settings_and_can_be_closed(self) -> None:
        svc = get_cache_service()
        assert svc is get_cache_service()
        assert svc.backend == "memory"
        await shutdown_cache()
        assert get_cache_service() is not svc
