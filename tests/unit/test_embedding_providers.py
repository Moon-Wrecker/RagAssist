"""Unit tests for Embedding Providers, Projector, Registry, and Fallback Service."""

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ragassist.platform.embeddings.adapters.openai_adapter import OpenAIEmbeddingAdapter
from ragassist.platform.embeddings.adapters.openai_compatible_adapter import (
    OpenAICompatibleEmbeddingAdapter,
)
from ragassist.platform.embeddings.adapters.sentence_transformers_adapter import (
    SentenceTransformersEmbeddingAdapter,
)
from ragassist.platform.embeddings.projector import DimensionProjector
from ragassist.platform.embeddings.registry import build_embedding_registry
from ragassist.platform.embeddings.service import EmbeddingService
from ragassist.shared.resilience import FallbackChain


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


# --- 1. DimensionProjector Tests ---


def test_dimension_projector_padding_cosine_invariance():
    """Mathematically assert that zero-padding preserves exact cosine similarity."""
    u = [1.0 / math.sqrt(3), 1.0 / math.sqrt(3), 1.0 / math.sqrt(3)]
    v = [1.0, 0.0, 0.0]

    orig_sim = cosine_similarity(u, v)

    projector = DimensionProjector(target_dimension=1536)
    u_pad = projector.project_vector(u)
    v_pad = projector.project_vector(v)

    assert len(u_pad) == 1536
    assert len(v_pad) == 1536
    pad_sim = cosine_similarity(u_pad, v_pad)

    assert pytest.approx(orig_sim, abs=1e-6) == pad_sim
    assert pytest.approx(1.0, abs=1e-6) == math.sqrt(sum(x * x for x in u_pad))


def test_dimension_projector_truncation():
    """Verify truncation for models with dimensions exceeding target."""
    projector = DimensionProjector(target_dimension=1536)
    vec = [0.1] * 2048
    projected = projector.project_vector(vec)

    assert len(projected) == 1536
    norm = math.sqrt(sum(x * x for x in projected))
    assert pytest.approx(1.0, abs=1e-6) == norm


# --- 2. OpenAI Embedding Adapter Tests ---


@pytest.mark.asyncio
async def test_openai_adapter_embed_documents_and_query():
    adapter = OpenAIEmbeddingAdapter(
        model_name="text-embedding-3-small", dimension=1536, batch_size=2
    )
    mock_vec = [0.05] * 1536

    with (
        patch(
            "langchain_openai.OpenAIEmbeddings.aembed_documents", new_callable=AsyncMock
        ) as mock_docs,
        patch(
            "langchain_openai.OpenAIEmbeddings.aembed_query", new_callable=AsyncMock
        ) as mock_query,
    ):
        mock_docs.side_effect = lambda batch: [mock_vec for _ in batch]
        mock_query.return_value = mock_vec

        chunks = ["chunk1", "chunk2", "chunk3"]
        docs_res = await adapter.embed_documents(chunks)

        assert len(docs_res) == 3
        assert len(docs_res[0]) == 1536
        # Batch size 2 for 3 items should trigger 2 calls
        assert mock_docs.call_count == 2

        query_res = await adapter.embed_query("search query")
        assert len(query_res) == 1536
        assert mock_query.call_count == 1


# --- 3. OpenAI-Compatible Adapter Tests ---


@pytest.mark.asyncio
async def test_openai_compatible_adapter_projection():
    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url="http://localhost:11434/v1",
        model_name="nomic-embed-text",
        dimension=1536,
    )
    # Mock Ollama returning 768-dim vector
    raw_768 = [0.1] * 768

    with (
        patch(
            "langchain_openai.OpenAIEmbeddings.aembed_documents", new_callable=AsyncMock
        ) as mock_docs,
        patch(
            "langchain_openai.OpenAIEmbeddings.aembed_query", new_callable=AsyncMock
        ) as mock_query,
    ):
        mock_docs.return_value = [raw_768]
        mock_query.return_value = raw_768

        docs = await adapter.embed_documents(["test"])
        query = await adapter.embed_query("test query")

        assert len(docs[0]) == 1536
        assert len(query) == 1536


# --- 4. SentenceTransformers Adapter Tests ---


@pytest.mark.asyncio
async def test_sentence_transformers_adapter_mocked():
    adapter = SentenceTransformersEmbeddingAdapter(
        model_name="all-MiniLM-L6-v2",
        target_dimension=1536,
        device="cpu",
    )
    mock_st = MagicMock()
    # 384-dim normalized vector
    mock_st.encode.return_value = [[1.0 / math.sqrt(384)] * 384 for _ in range(2)]

    with patch.object(adapter, "_get_model", return_value=mock_st):
        res = await adapter.embed_documents(["doc1", "doc2"])
        assert len(res) == 2
        assert len(res[0]) == 1536
        assert pytest.approx(1.0, abs=1e-5) == math.sqrt(sum(x * x for x in res[0]))


def test_sentence_transformers_missing_dependency_error():
    adapter = SentenceTransformersEmbeddingAdapter()
    with patch.dict("sys.modules", {"sentence_transformers": None}):
        with pytest.raises(ImportError) as exc_info:
            adapter._get_model()
        assert "requires 'sentence-transformers'" in str(exc_info.value)


def test_provider_registry_lookup_and_aliases():
    registry = build_embedding_registry()
    assert registry.is_registered("openai")
    assert registry.is_registered("sentence_transformers")
    assert registry.is_registered("ollama")
    assert registry.is_registered("local")

    with pytest.raises(KeyError):
        registry.create("non_existent_provider")


# --- 5. FallbackChain & EmbeddingService Tests ---


class FakeEmbeddingProvider:
    def __init__(
        self, name: str, dim: int = 1536, fail: bool = False, wrong_dim: bool = False
    ) -> None:
        self.name = name
        self._dim = dim
        self.fail = fail
        self.wrong_dim = wrong_dim

    def dimension(self) -> int:
        return self._dim

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise TimeoutError(f"Provider {self.name} timed out")
        dim = 512 if self.wrong_dim else self._dim
        return [[0.1] * dim for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        if self.fail:
            raise TimeoutError(f"Provider {self.name} timed out")
        dim = 512 if self.wrong_dim else self._dim
        return [0.1] * dim


@pytest.mark.asyncio
async def test_embedding_service_primary_success():
    p1 = FakeEmbeddingProvider("p1")
    p2 = FakeEmbeddingProvider("p2")
    chain = FallbackChain("test", [p1, p2])
    svc = EmbeddingService(chain, expected_dimension=1536)

    res = await svc.embed_query("hello")
    assert len(res) == 1536


@pytest.mark.asyncio
async def test_embedding_service_failover_on_exception():
    p1 = FakeEmbeddingProvider("p1", fail=True)
    p2 = FakeEmbeddingProvider("p2", fail=False)
    chain = FallbackChain("test", [p1, p2])
    svc = EmbeddingService(chain, expected_dimension=1536)

    res = await svc.embed_query("hello")
    assert len(res) == 1536


@pytest.mark.asyncio
async def test_embedding_service_failover_on_unacceptable_dim():
    p1 = FakeEmbeddingProvider("p1", wrong_dim=True)
    p2 = FakeEmbeddingProvider("p2", wrong_dim=False)
    chain = FallbackChain("test", [p1, p2])
    svc = EmbeddingService(chain, expected_dimension=1536)

    res = await svc.embed_documents(["doc1", "doc2"])
    assert len(res) == 2
    assert len(res[0]) == 1536


@pytest.mark.asyncio
async def test_embedding_service_all_members_fail():
    p1 = FakeEmbeddingProvider("p1", fail=True)
    p2 = FakeEmbeddingProvider("p2", fail=True)
    chain = FallbackChain("test", [p1, p2])
    svc = EmbeddingService(chain, expected_dimension=1536)

    with pytest.raises(RuntimeError) as exc_info:
        await svc.embed_query("hello")
    assert "All 2 members of FallbackChain 'test' failed" in str(exc_info.value)
