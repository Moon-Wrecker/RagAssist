"""Embedding cache (ADR 0015): query vectors per tenant, chunk vectors by content hash, fallback safety."""

from __future__ import annotations

import pytest
from fakes.embeddings import FakeEmbeddingProvider
from support.settings import make_settings

from ragassist.platform.cache import build_cache_service
from ragassist.platform.cache import keys as kinds
from ragassist.platform.cache.adapters.memory_adapter import InMemoryCache
from ragassist.platform.embeddings.service import EmbeddingService
from ragassist.shared.resilience import FallbackChain

DIM = 8
TENANT_A = "a0000000-0000-0000-0000-00000000000a"
TENANT_B = "b0000000-0000-0000-0000-00000000000b"


def cache_service(**settings: object):  # type: ignore[no-untyped-def]
    cfg = make_settings(**settings)
    return build_cache_service(cfg, InMemoryCache(max_entries=1000, max_value_bytes=65536))


def service(*providers: FakeEmbeddingProvider, cache=None) -> EmbeddingService:  # type: ignore[no-untyped-def]
    return EmbeddingService(
        FallbackChain(name="emb", members=list(providers)), expected_dimension=DIM, cache=cache
    )


class TestQueryVectors:
    async def test_a_repeated_query_is_embedded_once(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        svc = service(provider, cache=cache_service())
        first = await svc.embed_query_for(TENANT_A, "How do I reset my password?")
        second = await svc.embed_query_for(TENANT_A, "how do i  RESET my password?")  # normalised
        assert len(provider.queries) == 1
        assert second == pytest.approx(first, abs=1e-6)

    async def test_another_tenant_never_reuses_the_vector(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        svc = service(provider, cache=cache_service())
        await svc.embed_query_for(TENANT_A, "same question")
        await svc.embed_query_for(TENANT_B, "same question")
        assert len(provider.queries) == 2

    async def test_a_different_model_never_reuses_the_vector(self) -> None:
        shared = cache_service()
        one, two = FakeEmbeddingProvider(DIM, name="one"), FakeEmbeddingProvider(DIM, name="two")
        await service(one, cache=shared).embed_query_for(TENANT_A, "q")
        await service(two, cache=shared).embed_query_for(TENANT_A, "q")
        assert len(one.queries) == 1 and len(two.queries) == 1

    async def test_cache_off_is_the_plain_call(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        svc = service(provider, cache=build_cache_service(make_settings(CACHE_ENABLED=False)))
        await svc.embed_query_for(TENANT_A, "q")
        await svc.embed_query_for(TENANT_A, "q")
        assert len(provider.queries) == 2

    async def test_no_cache_object_is_the_plain_call(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        svc = service(provider)
        await svc.embed_query_for(TENANT_A, "q")
        await svc.embed_query_for(TENANT_A, "q")
        assert len(provider.queries) == 2

    async def test_a_fallback_vector_is_returned_but_never_cached(self) -> None:
        broken = FakeEmbeddingProvider(DIM, name="primary", fail_times=1)
        backup = FakeEmbeddingProvider(DIM, name="backup")
        svc = service(broken, backup, cache=cache_service())
        await svc.embed_query_for(TENANT_A, "q")
        assert backup.queries == ["q"]
        await svc.embed_query_for(
            TENANT_A, "q"
        )  # the primary has recovered: it answers, not a stale fallback
        assert broken.queries == ["q"]

    async def test_blank_text_is_not_cached(self) -> None:
        svc = service(FakeEmbeddingProvider(DIM), cache=cache_service())
        assert await svc.embed_query_for(TENANT_A, "  ") == [0.0] * DIM

    async def test_the_stored_key_holds_a_hash_not_the_text(self) -> None:
        cache = cache_service()
        svc = service(FakeEmbeddingProvider(DIM), cache=cache)
        await svc.embed_query_for(TENANT_A, "my invoice number is 4711")
        keys = list(cache.cache._items)  # type: ignore[attr-defined]
        assert keys and all("4711" not in k and TENANT_A in k for k in keys)
        assert all(k.split(":")[3] == kinds.EMBEDDING_QUERY for k in keys)


class TestDocumentVectors:
    async def test_chunks_with_a_known_content_hash_are_not_embedded_again(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        svc = service(provider, cache=cache_service())
        first = await svc.embed_documents_for(TENANT_A, ["alpha", "beta"])
        second = await svc.embed_documents_for(TENANT_A, ["alpha", "beta", "gamma"])
        assert provider.document_batches == [["alpha", "beta"], ["gamma"]]
        assert second[:2] == [pytest.approx(v, abs=1e-6) for v in first]
        assert len(second) == 3

    async def test_order_is_preserved_when_hits_and_misses_mix(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        svc = service(provider, cache=cache_service())
        await svc.embed_documents_for(TENANT_A, ["b"])
        mixed = await svc.embed_documents_for(TENANT_A, ["a", "b", "c"])
        plain = await service(FakeEmbeddingProvider(DIM)).embed_documents(["a", "b", "c"])
        assert mixed == [pytest.approx(v, abs=1e-6) for v in plain]

    async def test_another_tenant_embeds_its_own_chunks(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        svc = service(provider, cache=cache_service())
        await svc.embed_documents_for(TENANT_A, ["alpha"])
        await svc.embed_documents_for(TENANT_B, ["alpha"])
        assert provider.document_batches == [["alpha"], ["alpha"]]

    async def test_without_a_cache_it_is_embed_documents(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        svc = service(provider)
        await svc.embed_documents_for(TENANT_A, ["a", "b"])
        await svc.embed_documents_for(TENANT_A, ["a", "b"])
        assert provider.document_batches == [["a", "b"], ["a", "b"]]

    async def test_empty_input(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        assert (
            await service(provider, cache=cache_service()).embed_documents_for(TENANT_A, []) == []
        )
        assert provider.document_batches == []
