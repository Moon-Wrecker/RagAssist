"""Cache platform (ADR 0015): port, adapters, key rules and the process-wide facade accessor."""

from __future__ import annotations

from ragassist.platform.cache.keys import CacheKeyBuilder, InvalidCacheKey, normalise_text
from ragassist.platform.cache.ports import Cache, CacheError, CacheStats
from ragassist.platform.cache.service import GLOBAL_CORPUS, CacheService, CacheTTLs
from ragassist.shared.config.settings import Settings
from ragassist.shared.counters import SharedCounters

__all__ = [
    "GLOBAL_CORPUS",
    "Cache",
    "CacheError",
    "CacheKeyBuilder",
    "CacheService",
    "CacheStats",
    "CacheTTLs",
    "InvalidCacheKey",
    "build_cache",
    "build_cache_service",
    "get_shared_counters",
    "get_cache_service",
    "normalise_text",
    "reset_cache_service",
    "shutdown_cache",
]


def build_cache(settings: Settings) -> Cache:
    """The adapter ``settings`` ask for: a null cache when disabled, else memory or Redis."""
    if not settings.CACHE_ENABLED:
        from ragassist.platform.cache.adapters.null_adapter import NullCache

        return NullCache()
    if settings.CACHE_BACKEND == "redis":
        from ragassist.platform.cache.adapters.redis_adapter import RedisCache

        return RedisCache(
            url=settings.CACHE_REDIS_URL,
            password=settings.CACHE_REDIS_PASSWORD,
            timeout_seconds=settings.CACHE_REDIS_TIMEOUT_SECONDS,
            max_value_bytes=settings.CACHE_MAX_VALUE_BYTES,
        )
    from ragassist.platform.cache.adapters.memory_adapter import InMemoryCache

    return InMemoryCache(
        max_entries=settings.CACHE_MAX_ENTRIES, max_value_bytes=settings.CACHE_MAX_VALUE_BYTES
    )


def build_cache_service(settings: Settings, cache: Cache | None = None) -> CacheService:
    return CacheService(
        cache or build_cache(settings),
        CacheKeyBuilder(prefix=settings.CACHE_KEY_PREFIX, secret=settings.SECRET_KEY),
        CacheTTLs(
            embedding_query=settings.CACHE_EMBEDDING_QUERY_TTL_SECONDS,
            embedding_document=settings.CACHE_EMBEDDING_DOCUMENT_TTL_SECONDS,
            retrieval=settings.CACHE_RETRIEVAL_TTL_SECONDS,
            decision=settings.CACHE_DECISION_TTL_SECONDS,
            corpus_version=settings.CACHE_CORPUS_VERSION_TTL_SECONDS,
        ),
    )


_service: CacheService | None = None


def get_cache_service() -> CacheService:
    """The process-wide cache facade, built from settings on first use."""
    global _service
    if _service is None:
        from ragassist.shared.config.settings import get_settings

        _service = build_cache_service(get_settings())
        from ragassist.platform.cache.metrics import install_cache_metrics

        install_cache_metrics(_service)
    return _service


def get_shared_counters() -> SharedCounters | None:
    """Counters shared between replicas, or ``None`` unless the cache backend is Redis (ADR 0015).

    With the in-memory backend (or the cache disabled) callers keep their own exact in-process logic.
    """
    from ragassist.shared.config.settings import get_settings

    settings = get_settings()
    if not settings.CACHE_ENABLED or settings.CACHE_BACKEND != "redis":
        return None
    from ragassist.platform.cache.counters import CacheCounters

    return CacheCounters(get_cache_service())


def reset_cache_service() -> None:
    """Forget the facade (test isolation, settings reload). Does not close the old adapter."""
    global _service
    _service = None


async def shutdown_cache() -> None:
    """Close the adapter (the Redis connection pool) and forget the facade."""
    global _service
    service, _service = _service, None
    if service is not None:
        await service.aclose()
