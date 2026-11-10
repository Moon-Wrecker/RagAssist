"""High-level Embedding Service with automatic FallbackChain resilience."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from ragassist.platform.cache import keys as cache_kinds
from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.platform.embeddings.registry import build_embedding_registry
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.resilience import FallbackChain

if TYPE_CHECKING:
    from ragassist.platform.cache import CacheService

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Service orchestrating dense embeddings with automatic failover across providers."""

    def __init__(
        self,
        chain: FallbackChain[EmbeddingProvider],
        expected_dimension: int = 1536,
        cache: CacheService | None = None,
    ) -> None:
        self._chain = chain
        self._expected_dimension = expected_dimension
        self._cache = cache if cache is not None and cache.enabled else None

    @property
    def dimension(self) -> int:
        return self._expected_dimension

    @property
    def members(self) -> list[EmbeddingProvider]:
        return list(self._chain.members)

    # -- cached variants (ADR 0015) -------------------------------------------------------------------------------
    def _cache_context(self) -> tuple[str, ...]:
        """Provider, model and size that produced the vectors: a different one must never reuse an entry.

        Only the chain's first member is cached. When it fails and a fallback answers, that vector comes from
        another model than the stored corpus, so it is returned to the caller but never written to the cache.
        """
        primary = self._chain.members[0]
        return (
            str(getattr(primary, "name", type(primary).__name__)),
            str(getattr(primary, "model_name", "")),
            str(self._expected_dimension),
        )

    async def embed_query_for(self, tenant_id: object, text: str) -> list[float]:
        """``embed_query`` with the result cached for this tenant (key: tenant, provider, model, hash of the text)."""
        if self._cache is None or not text or not text.strip():
            return await self.embed_query(text)
        cache, ttl = self._cache, self._cache.ttls.embedding_query
        key = cache.keys.key(
            cache_kinds.EMBEDDING_QUERY, tenant_id, text=text, context=self._cache_context()
        )
        cached = await cache.get_vector(cache_kinds.EMBEDDING_QUERY, key, self._expected_dimension)
        if cached is not None:
            return cached

        async def _operation(provider: EmbeddingProvider) -> list[float]:
            return await provider.embed_query(text)

        vector, used = await self._chain.execute(
            operation=_operation, is_acceptable=lambda v: len(v) == self._expected_dimension
        )
        if used is self._chain.members[0]:
            await cache.set_vector(cache_kinds.EMBEDDING_QUERY, key, vector, ttl)
        return vector

    async def embed_documents_for(self, tenant_id: object, texts: list[str]) -> list[list[float]]:
        """``embed_documents`` that skips every text whose content hash already has a vector for this tenant.

        Used by ingestion and re-indexing: an unchanged chunk is not sent to the provider again. Identical
        output to ``embed_documents``; with the cache off it is that call.
        """
        if self._cache is None or not texts:
            return await self.embed_documents(texts)
        cache, ttl = self._cache, self._cache.ttls.embedding_document
        context = self._cache_context()
        keys = [
            cache.keys.key(cache_kinds.EMBEDDING_DOCUMENT, tenant_id, text=t, context=context)
            for t in texts
        ]
        vectors: list[list[float] | None] = []
        for key in keys:
            vectors.append(
                await cache.get_vector(cache_kinds.EMBEDDING_DOCUMENT, key, self._expected_dimension)
            )
        missing = [i for i, v in enumerate(vectors) if v is None]
        if missing:
            fresh, used = await self._embed_documents_with_provider([texts[i] for i in missing])
            for i, vector in zip(missing, fresh, strict=True):
                vectors[i] = vector
                if used is self._chain.members[0]:
                    await cache.set_vector(cache_kinds.EMBEDDING_DOCUMENT, keys[i], vector, ttl)
        return [v for v in vectors if v is not None]

    async def _embed_documents_with_provider(
        self, texts: list[str]
    ) -> tuple[list[list[float]], EmbeddingProvider]:
        async def _operation(provider: EmbeddingProvider) -> list[list[float]]:
            return await provider.embed_documents(texts)

        def _is_acceptable(vectors: list[list[float]]) -> bool:
            return len(vectors) == len(texts) and all(
                len(v) == self._expected_dimension for v in vectors
            )

        return await self._chain.execute(operation=_operation, is_acceptable=_is_acceptable)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        async def _operation(provider: EmbeddingProvider) -> list[list[float]]:
            return await provider.embed_documents(texts)

        def _is_acceptable(vectors: list[list[float]]) -> bool:
            if not vectors or len(vectors) != len(texts):
                return False
            # Verify each vector matches required pgvector dimension
            return all(len(v) == self._expected_dimension for v in vectors)

        vectors, _used_provider = await self._chain.execute(
            operation=_operation,
            is_acceptable=_is_acceptable,
        )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        if not text or not text.strip():
            return [0.0] * self._expected_dimension

        async def _operation(provider: EmbeddingProvider) -> list[float]:
            return await provider.embed_query(text)

        def _is_acceptable(vector: list[float]) -> bool:
            return len(vector) == self._expected_dimension

        vector, _used_provider = await self._chain.execute(
            operation=_operation,
            is_acceptable=_is_acceptable,
        )
        return vector


def build_embedding_service(
    settings: Settings | None = None, cache: CacheService | None = None
) -> EmbeddingService:
    """Factory creating an EmbeddingService initialized with configured FallbackChain.

    ``cache`` turns on the tenant-scoped query and document embedding cache (``embed_query_for`` and
    ``embed_documents_for``); without it those methods are the plain calls.
    """
    cfg = settings or get_settings()
    registry = build_embedding_registry(cfg)

    # Parse fallback chain string: e.g. "openai,sentence_transformers"
    chain_keys_raw = getattr(cfg, "EMBEDDING_FALLBACK_CHAIN", "openai,sentence_transformers")
    chain_keys = [k.strip().lower() for k in chain_keys_raw.split(",") if k.strip()]

    providers: list[EmbeddingProvider] = []
    for key in chain_keys:
        if registry.is_registered(key):
            providers.append(registry.create(key))
        else:
            logger.warning("embedding_service.unknown_provider", key=key)

    if not providers:
        # Fallback to default openai adapter
        providers = [registry.create("openai")]

    chain = FallbackChain[EmbeddingProvider](name="embeddings_chain", members=providers)
    return EmbeddingService(chain=chain, expected_dimension=cfg.EMBEDDING_DIMENSION, cache=cache)
