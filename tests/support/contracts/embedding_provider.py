"""Contract for ``EmbeddingProvider`` implementations (async port)."""

from __future__ import annotations

import math

import pytest
from langchain_core.embeddings import Embeddings

from ragassist.platform.embeddings.ports import EmbeddingProvider


class EmbeddingProviderContract:
    """Subclass and provide ``provider``. Set ``deterministic = False`` for providers whose vectors
    legitimately vary between calls."""

    deterministic: bool = True
    unit_length: bool = False

    @pytest.fixture
    def provider(self) -> EmbeddingProvider:  # pragma: no cover - overridden
        raise NotImplementedError

    def test_conforms_to_the_port(self, provider: EmbeddingProvider) -> None:
        assert isinstance(provider, EmbeddingProvider)

    def test_has_a_name(self, provider: EmbeddingProvider) -> None:
        assert isinstance(provider.name, str) and provider.name

    def test_dimension_is_a_positive_int(self, provider: EmbeddingProvider) -> None:
        assert isinstance(provider.dimension(), int) and provider.dimension() > 0

    async def test_query_vector_has_the_declared_dimension(
        self, provider: EmbeddingProvider
    ) -> None:
        vector = await provider.embed_query("how do I rotate my API key?")
        assert len(vector) == provider.dimension()
        assert all(isinstance(x, float) and math.isfinite(x) for x in vector)

    async def test_document_vectors_have_the_declared_dimension(
        self, provider: EmbeddingProvider
    ) -> None:
        vectors = await provider.embed_documents(["alpha", "beta", "gamma"])
        assert len(vectors) == 3
        assert {len(v) for v in vectors} == {provider.dimension()}

    async def test_empty_batch_gives_empty_result(self, provider: EmbeddingProvider) -> None:
        assert await provider.embed_documents([]) == []

    async def test_result_order_follows_input_order(self, provider: EmbeddingProvider) -> None:
        if not self.deterministic:
            pytest.skip("provider is not deterministic")
        texts = ["first", "second", "third"]
        batch = await provider.embed_documents(texts)
        single = [(await provider.embed_documents([t]))[0] for t in texts]
        for got, expected in zip(batch, single, strict=True):
            assert got == pytest.approx(expected, abs=1e-5)

    async def test_same_text_gives_the_same_vector(self, provider: EmbeddingProvider) -> None:
        if not self.deterministic:
            pytest.skip("provider is not deterministic")
        a = await provider.embed_query("same text")
        b = await provider.embed_query("same text")
        assert a == pytest.approx(b, abs=1e-6)

    async def test_different_texts_give_different_vectors(
        self, provider: EmbeddingProvider
    ) -> None:
        if not self.deterministic:
            pytest.skip("provider is not deterministic")
        a = await provider.embed_query("billing and invoices")
        b = await provider.embed_query("quantum chromodynamics")
        assert a != b

    async def test_unit_length_when_promised(self, provider: EmbeddingProvider) -> None:
        if not self.unit_length:
            pytest.skip("provider does not promise unit-length vectors")
        norm = math.sqrt(sum(x * x for x in await provider.embed_query("normalise me")))
        assert norm == pytest.approx(1.0, abs=1e-4)

    async def test_unicode_and_long_text_are_accepted(self, provider: EmbeddingProvider) -> None:
        vectors = await provider.embed_documents(["日本語のテキスト 🚀", "é" * 5000])
        assert len(vectors) == 2

    def test_exposes_a_langchain_embeddings_bridge(self, provider: EmbeddingProvider) -> None:
        assert isinstance(provider.as_langchain_embeddings(), Embeddings)
