"""EmbeddingService (fallback chain + dimension guard) and the provider registry."""

from __future__ import annotations

import pytest
from fakes.embeddings import FakeEmbeddingProvider
from support.settings import make_settings

from ragassist.platform.embeddings.adapters.openai_adapter import OpenAIEmbeddingAdapter
from ragassist.platform.embeddings.adapters.openai_compatible_adapter import (
    OpenAICompatibleEmbeddingAdapter,
)
from ragassist.platform.embeddings.adapters.sentence_transformers_adapter import (
    SentenceTransformersEmbeddingAdapter,
)
from ragassist.platform.embeddings.registry import build_embedding_registry
from ragassist.platform.embeddings.service import EmbeddingService, build_embedding_service
from ragassist.shared.resilience import FallbackChain

DIM = 8


def service(*providers: FakeEmbeddingProvider, dimension: int = DIM) -> EmbeddingService:
    return EmbeddingService(
        FallbackChain(name="emb", members=list(providers)), expected_dimension=dimension
    )


class WrongShape(FakeEmbeddingProvider):
    """Returns vectors of the wrong dimension, or the wrong number of vectors."""

    def __init__(self, *, dimension: int = 4, drop_last: bool = False, name: str = "wrong") -> None:
        super().__init__(dimension, name=name)
        self.drop_last = drop_last

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = await super().embed_documents(texts)
        return vectors[:-1] if self.drop_last else vectors


class TestDocuments:
    async def test_embeds_through_the_first_healthy_provider(self) -> None:
        first, second = (
            FakeEmbeddingProvider(DIM, name="first"),
            FakeEmbeddingProvider(DIM, name="second"),
        )
        vectors = await service(first, second).embed_documents(["a", "b"])
        assert (
            len(vectors) == 2
            and first.document_batches == [["a", "b"]]
            and second.document_batches == []
        )

    async def test_empty_input_returns_empty_without_calling_a_provider(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        assert await service(provider).embed_documents([]) == []
        assert provider.document_batches == []

    async def test_a_failing_provider_falls_through(self) -> None:
        broken, healthy = (
            FakeEmbeddingProvider(DIM, name="b", fail_times=5),
            FakeEmbeddingProvider(DIM, name="h"),
        )
        assert len(await service(broken, healthy).embed_documents(["a"])) == 1

    async def test_vectors_of_the_wrong_dimension_are_rejected(self) -> None:
        vectors = await service(
            WrongShape(dimension=4), FakeEmbeddingProvider(DIM)
        ).embed_documents(["a"])
        assert {len(v) for v in vectors} == {DIM}

    async def test_a_short_result_list_is_rejected(self) -> None:
        vectors = await service(
            WrongShape(dimension=DIM, drop_last=True), FakeEmbeddingProvider(DIM)
        ).embed_documents(["a", "b"])
        assert len(vectors) == 2

    async def test_when_every_provider_fails_the_error_surfaces(self) -> None:
        with pytest.raises(RuntimeError):
            await service(
                FakeEmbeddingProvider(DIM, fail_times=9), FakeEmbeddingProvider(DIM, fail_times=9)
            ).embed_documents(["a"])

    async def test_when_every_provider_returns_bad_shapes_it_does_not_return_them(self) -> None:
        with pytest.raises(RuntimeError):
            await service(WrongShape(dimension=4)).embed_documents(["a"])

    async def test_order_is_preserved(self) -> None:
        provider = FakeEmbeddingProvider(DIM)
        texts = [f"t{i}" for i in range(20)]
        vectors = await service(provider).embed_documents(texts)
        assert vectors == [await provider.embed_query(t) for t in texts]


class TestQueries:
    async def test_embeds_a_query(self) -> None:
        assert len(await service(FakeEmbeddingProvider(DIM)).embed_query("hello")) == DIM

    @pytest.mark.parametrize("text", ["", "   ", "\n\t"])
    async def test_blank_queries_give_a_zero_vector_without_calling_a_provider(
        self, text: str
    ) -> None:
        provider = FakeEmbeddingProvider(DIM)
        assert await service(provider).embed_query(text) == [0.0] * DIM
        assert provider.queries == []

    async def test_query_falls_through_on_failure(self) -> None:
        vector = await service(
            FakeEmbeddingProvider(DIM, fail_times=3), FakeEmbeddingProvider(DIM)
        ).embed_query("x")
        assert len(vector) == DIM

    async def test_wrong_dimension_query_vectors_are_rejected(self) -> None:
        with pytest.raises(RuntimeError):
            await service(WrongShape(dimension=4)).embed_query("x")

    async def test_document_and_query_vectors_live_in_the_same_space(self) -> None:
        svc = service(FakeEmbeddingProvider(DIM))
        (doc,) = await svc.embed_documents(["same text"])
        assert doc == pytest.approx(await svc.embed_query("same text"))


class TestProperties:
    def test_dimension_is_reported(self) -> None:
        assert service(FakeEmbeddingProvider(DIM), dimension=DIM).dimension == DIM

    def test_members_returns_a_defensive_copy(self) -> None:
        svc = service(FakeEmbeddingProvider(DIM))
        svc.members.clear()
        assert len(svc.members) == 1


class TestFactory:
    def test_chain_follows_the_configured_order(self) -> None:
        svc = build_embedding_service(
            make_settings(
                EMBEDDING_FALLBACK_CHAIN="sentence_transformers, openai_compatible, openai"
            )
        )
        assert [m.name for m in svc.members] == [
            "sentence_transformers",
            "openai_compatible",
            "openai",
        ]

    def test_dimension_comes_from_settings(self) -> None:
        assert build_embedding_service(make_settings(EMBEDDING_DIMENSION=768)).dimension == 768

    def test_unknown_providers_are_skipped(self) -> None:
        svc = build_embedding_service(make_settings(EMBEDDING_FALLBACK_CHAIN="nonsense,openai"))
        assert [m.name for m in svc.members] == ["openai"]

    @pytest.mark.parametrize("value", ["", " , ", "nonsense"])
    def test_an_unusable_chain_defaults_to_openai(self, value: str) -> None:
        svc = build_embedding_service(make_settings(EMBEDDING_FALLBACK_CHAIN=value))
        assert [m.name for m in svc.members] == ["openai"]

    def test_chain_keys_are_case_insensitive(self) -> None:
        svc = build_embedding_service(make_settings(EMBEDDING_FALLBACK_CHAIN="OpenAI,Local"))
        assert [m.name for m in svc.members] == ["openai", "sentence_transformers"]

    def test_default_chain_matches_env_example(self) -> None:
        assert make_settings().EMBEDDING_FALLBACK_CHAIN == "openai,sentence_transformers"

    def test_provider_setting_and_chain_are_consistent(self) -> None:
        """EMBEDDING_PROVIDER names the primary; it must head the default chain."""
        settings = make_settings()
        assert settings.EMBEDDING_FALLBACK_CHAIN.split(",")[0] == settings.EMBEDDING_PROVIDER


class TestRegistry:
    @pytest.mark.parametrize(
        ("key", "cls"),
        [
            ("openai", OpenAIEmbeddingAdapter),
            ("openai_compatible", OpenAICompatibleEmbeddingAdapter),
            ("ollama", OpenAICompatibleEmbeddingAdapter),
            ("sentence_transformers", SentenceTransformersEmbeddingAdapter),
            ("local", SentenceTransformersEmbeddingAdapter),
        ],
    )
    def test_keys_resolve_to_the_documented_adapters(self, key: str, cls: type) -> None:
        assert isinstance(build_embedding_registry(make_settings()).create(key), cls)

    def test_unknown_key_lists_the_available_providers(self) -> None:
        with pytest.raises(Exception) as info:
            build_embedding_registry(make_settings()).create("nope")
        assert "openai" in str(info.value)

    def test_each_create_builds_a_fresh_instance(self) -> None:
        registry = build_embedding_registry(make_settings())
        assert registry.create("local") is not registry.create("local")
