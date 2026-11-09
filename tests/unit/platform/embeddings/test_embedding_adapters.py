"""Embedding adapters against the shared contract.

* OpenAI-compatible and OpenAI adapters run for real against a loopback server (genuine SDK ->
  HTTP -> JSON path, no private-API coupling).
* SentenceTransformers is exercised with stub ``sentence_transformers``/``torch`` modules (no
  numpy/torch needed) so model loading, device choice and thread offloading are still verified.
* The deterministic fake provider is itself checked against the contract.
"""

from __future__ import annotations

import asyncio
import math
import sys
import threading
import types
from typing import Any

import openai
import pytest
import tiktoken
from fakes.embeddings import FakeEmbeddingProvider, vector_for
from support.contracts import EmbeddingProviderContract
from support.defects import defect
from support.fake_openai_server import FakeOpenAIServer
from support.settings import make_settings

from ragassist.platform.embeddings.adapters.openai_adapter import OpenAIEmbeddingAdapter
from ragassist.platform.embeddings.adapters.openai_compatible_adapter import (
    OpenAICompatibleEmbeddingAdapter,
)
from ragassist.platform.embeddings.adapters.sentence_transformers_adapter import (
    SentenceTransformersEmbeddingAdapter,
)
from ragassist.platform.embeddings.ports import EmbeddingProvider

DIM = 8


class _ByteEncoding:
    """Byte-level stand-in for a tiktoken encoding: deterministic tokens, nothing to download."""

    def encode(self, text: str, **_kwargs: Any) -> list[int]:
        return list(text.encode("utf-8"))

    def encode_ordinary(self, text: str) -> list[int]:
        return self.encode(text)

    def decode(self, tokens: list[int], **_kwargs: Any) -> str:
        return bytes(tokens).decode("utf-8", errors="replace")


@pytest.fixture
def compatible(embedding_server: FakeOpenAIServer):
    def build(**kwargs: Any) -> OpenAICompatibleEmbeddingAdapter:
        settings = kwargs.pop("settings", None) or make_settings(
            EMBEDDING_DIMENSION=kwargs.pop("dim", DIM)
        )
        return OpenAICompatibleEmbeddingAdapter(
            base_url=embedding_server.base_url,
            api_key=kwargs.pop("api_key", "secret-token"),
            settings=settings,
            **kwargs,
        )

    return build


@pytest.fixture
def openai_adapter(embedding_server: FakeOpenAIServer, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "OPENAI_API_BASE", embedding_server.base_url
    )  # legacy name, honoured by older SDKs
    monkeypatch.setenv(
        "OPENAI_BASE_URL", embedding_server.base_url
    )  # current name, the only one newer SDKs read
    # langchain-openai tokenises with tiktoken, which downloads its BPE file on first use. That is a real
    # network call (blocked in CI), and the loopback server only hashes whatever items it receives.
    monkeypatch.setattr(tiktoken, "encoding_for_model", lambda *_a, **_k: _ByteEncoding())
    monkeypatch.setattr(tiktoken, "get_encoding", lambda *_a, **_k: _ByteEncoding())

    def build(**kwargs: Any) -> OpenAIEmbeddingAdapter:
        base_url = kwargs.pop("base_url", embedding_server.base_url)
        settings = make_settings(
            OPENAI_API_KEY="sk-test",
            OPENAI_BASE_URL=base_url,
            EMBEDDING_DIMENSION=DIM,
            **kwargs.pop("settings_overrides", {}),
        )
        return OpenAIEmbeddingAdapter(base_url=base_url, settings=settings, **kwargs)

    return build


# --------------------------------------------------------------------------- contract subclasses
class TestFakeProviderContract(EmbeddingProviderContract):
    unit_length = True

    @pytest.fixture
    def provider(self) -> EmbeddingProvider:
        return FakeEmbeddingProvider(dimension=DIM)


class TestOpenAICompatibleContract(EmbeddingProviderContract):
    unit_length = True

    @pytest.fixture
    def provider(self, compatible) -> EmbeddingProvider:  # type: ignore[no-untyped-def]
        return compatible()


class TestOpenAIContract(EmbeddingProviderContract):
    unit_length = True

    @pytest.fixture
    def provider(self, openai_adapter) -> EmbeddingProvider:  # type: ignore[no-untyped-def]
        return openai_adapter()


# --------------------------------------------------------------------------- OpenAI-compatible
class TestOpenAICompatible:
    async def test_posts_the_configured_model_to_the_embeddings_route(
        self, compatible, embedding_server
    ) -> None:
        await compatible(model_name="my-embedder").embed_query("hello")
        request = embedding_server.embedding_requests[-1]
        assert request.path.endswith("/embeddings")
        assert request.body["model"] == "my-embedder"

    async def test_sends_the_api_key_as_a_bearer_token(self, compatible, embedding_server) -> None:
        await compatible(api_key="local-key").embed_query("hello")
        assert embedding_server.requests[-1].headers["authorization"] == "Bearer local-key"

    async def test_base_url_and_key_default_from_settings(self, embedding_server) -> None:
        adapter = OpenAICompatibleEmbeddingAdapter(
            settings=make_settings(
                OPENAI_COMPATIBLE_BASE_URL=embedding_server.base_url,
                OPENAI_COMPATIBLE_API_KEY="from-settings",
                EMBEDDING_DIMENSION=DIM,
            )
        )
        await adapter.embed_query("x")
        assert embedding_server.requests[-1].headers["authorization"] == "Bearer from-settings"

    @pytest.mark.parametrize(
        ("count", "batch_size", "expected"),
        [
            (0, 3, []),
            (1, 3, [1]),
            (2, 3, [2]),
            (3, 3, [3]),
            (4, 3, [3, 1]),
            (7, 3, [3, 3, 1]),
            (6, 3, [3, 3]),
        ],
    )
    async def test_documents_are_sent_in_batches(
        self, compatible, embedding_server, count, batch_size, expected
    ) -> None:
        vectors = await compatible(batch_size=batch_size).embed_documents(
            [f"doc {i}" for i in range(count)]
        )
        assert len(vectors) == count
        assert embedding_server.batch_sizes() == expected

    async def test_batch_size_defaults_from_settings(self, embedding_server) -> None:
        adapter = OpenAICompatibleEmbeddingAdapter(
            base_url=embedding_server.base_url,
            settings=make_settings(EMBEDDING_BATCH_SIZE=2, EMBEDDING_DIMENSION=DIM),
        )
        await adapter.embed_documents(["a", "b", "c", "d", "e"])
        assert embedding_server.batch_sizes() == [2, 2, 1]

    async def test_order_is_preserved_across_batches(self, compatible) -> None:
        texts = [f"text-{i}" for i in range(7)]
        batched = await compatible(batch_size=3).embed_documents(texts)
        one_by_one = [await compatible().embed_query(t) for t in texts]
        for a, b in zip(batched, one_by_one, strict=True):
            assert a == pytest.approx(b, abs=1e-6)

    async def test_short_server_vectors_are_padded_to_the_database_dimension(
        self, compatible, embedding_server
    ) -> None:
        embedding_server.default_dimension = 4
        vector = await compatible(dim=8).embed_query("pad me")
        assert len(vector) == 8 and vector[4:] == [0.0] * 4
        assert math.sqrt(sum(x * x for x in vector)) == pytest.approx(1.0)

    async def test_long_server_vectors_are_truncated_to_the_database_dimension(
        self, compatible, embedding_server
    ) -> None:
        embedding_server.default_dimension = 16
        vectors = await compatible(dim=8).embed_documents(["a", "b"])
        assert {len(v) for v in vectors} == {8}

    async def test_a_hung_server_times_out_instead_of_blocking(
        self, compatible, embedding_server
    ) -> None:
        embedding_server.delay_seconds = 3.0
        adapter = compatible(timeout=0.3)
        with pytest.raises((asyncio.TimeoutError, openai.APITimeoutError)):
            await asyncio.wait_for(adapter.embed_query("slow"), timeout=2.5)

    async def test_authentication_errors_surface_as_exceptions(
        self, compatible, embedding_server
    ) -> None:
        embedding_server.fail_next(401, "bad key")
        with pytest.raises(openai.AuthenticationError):
            await compatible().embed_query("x")

    async def test_a_transient_server_error_is_retried_by_the_client(
        self, compatible, embedding_server
    ) -> None:
        embedding_server.fail_next(500, "flaky")
        vector = await compatible().embed_query("x")
        assert len(vector) == DIM
        assert len(embedding_server.embedding_requests) == 2

    async def test_langchain_bridge_uses_the_same_endpoint(
        self, compatible, embedding_server
    ) -> None:
        bridge = compatible().as_langchain_embeddings()
        vector = await bridge.aembed_query("via bridge")
        assert len(vector) == DIM and embedding_server.embedding_requests

    async def test_parallel_calls_do_not_interfere(self, compatible) -> None:
        adapter = compatible()
        results = await asyncio.gather(*[adapter.embed_query(f"q{i}") for i in range(10)])
        for i, vector in enumerate(results):
            assert vector == pytest.approx(await adapter.embed_query(f"q{i}"), abs=1e-6)

    @defect("DEFECT-28")
    async def test_timeout_follows_the_embedding_timeout_setting(self, embedding_server) -> None:
        embedding_server.delay_seconds = 1.5
        adapter = OpenAICompatibleEmbeddingAdapter(
            base_url=embedding_server.base_url,
            settings=make_settings(EMBEDDING_TIMEOUT_SECONDS=0.3, EMBEDDING_DIMENSION=DIM),
        )
        with pytest.raises((asyncio.TimeoutError, openai.APITimeoutError)):
            await adapter.embed_query("slow")


# --------------------------------------------------------------------------- OpenAI
class TestOpenAI:
    async def test_requests_the_configured_dimension_for_v3_models(
        self, openai_adapter, embedding_server
    ) -> None:
        await openai_adapter(
            settings_overrides={"EMBEDDING_MODEL": "text-embedding-3-small"}
        ).embed_query("x")
        assert embedding_server.embedding_requests[-1].body["dimensions"] == DIM

    async def test_does_not_send_dimensions_to_models_that_reject_it(
        self, openai_adapter, embedding_server
    ) -> None:
        await openai_adapter(
            settings_overrides={"EMBEDDING_MODEL": "text-embedding-ada-002"}
        ).embed_query("x")
        assert "dimensions" not in embedding_server.embedding_requests[-1].body

    async def test_sends_the_openai_key(self, openai_adapter, embedding_server) -> None:
        await openai_adapter().embed_query("x")
        assert embedding_server.requests[-1].headers["authorization"] == "Bearer sk-test"

    async def test_documents_are_batched_by_embedding_batch_size(
        self, openai_adapter, embedding_server
    ) -> None:
        adapter = openai_adapter(batch_size=4)
        await adapter.embed_documents([f"d{i}" for i in range(10)])
        assert embedding_server.batch_sizes() == [4, 4, 2]

    async def test_missing_api_key_does_not_crash_construction(self) -> None:
        adapter = OpenAIEmbeddingAdapter(settings=make_settings(OPENAI_API_KEY=""))
        assert adapter.dimension() == 1536

    async def test_a_dummy_key_is_not_logged(self, capsys: pytest.CaptureFixture[str]) -> None:
        OpenAIEmbeddingAdapter(settings=make_settings(OPENAI_API_KEY=""))
        captured = capsys.readouterr()
        assert "dummy-key" not in captured.out + captured.err

    @defect("DEFECT-28")
    async def test_timeout_follows_the_embedding_timeout_setting(
        self, openai_adapter, embedding_server
    ) -> None:
        embedding_server.delay_seconds = 1.5
        adapter = openai_adapter(settings_overrides={"EMBEDDING_TIMEOUT_SECONDS": 0.3})
        with pytest.raises((asyncio.TimeoutError, openai.APITimeoutError)):
            await adapter.embed_query("slow")


# --------------------------------------------------------------------------- sentence-transformers
class StubSentenceTransformer:
    instances: list[StubSentenceTransformer] = []

    def __init__(self, name: str, device: str = "cpu") -> None:
        self.name, self.device = name, device
        self.encode_calls: list[dict[str, Any]] = []
        self.threads: list[int] = []
        StubSentenceTransformer.instances.append(self)

    def encode(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        self.encode_calls.append({"texts": list(texts), **kwargs})
        self.threads.append(threading.get_ident())
        return [vector_for(t, 24) for t in texts]  # 24 -> projected to the target dimension


@pytest.fixture
def st_stubs(monkeypatch: pytest.MonkeyPatch):
    StubSentenceTransformer.instances = []
    cuda = types.SimpleNamespace(is_available=lambda: False)
    torch = types.SimpleNamespace(cuda=cuda)
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = StubSentenceTransformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setitem(sys.modules, "torch", torch)
    return types.SimpleNamespace(cuda=cuda, instances=StubSentenceTransformer.instances)


def st_adapter(**kwargs: Any) -> SentenceTransformersEmbeddingAdapter:
    return SentenceTransformersEmbeddingAdapter(
        settings=make_settings(EMBEDDING_DIMENSION=DIM), **kwargs
    )


class TestSentenceTransformersContract(EmbeddingProviderContract):
    unit_length = True

    @pytest.fixture
    def provider(self, st_stubs) -> EmbeddingProvider:  # type: ignore[no-untyped-def]
        return st_adapter()


class TestSentenceTransformers:
    async def test_the_model_is_loaded_lazily_and_only_once(self, st_stubs) -> None:
        adapter = st_adapter()
        assert st_stubs.instances == []
        await adapter.embed_query("a")
        await adapter.embed_documents(["b", "c"])
        assert len(st_stubs.instances) == 1

    async def test_construction_does_not_need_the_ml_extras(self) -> None:
        assert st_adapter().dimension() == DIM

    async def test_empty_batch_does_not_load_the_model(self, st_stubs) -> None:
        assert await st_adapter().embed_documents([]) == []
        assert st_stubs.instances == []

    @pytest.mark.parametrize(("cuda", "expected"), [(True, "cuda"), (False, "cpu")])
    async def test_device_is_chosen_from_cuda_availability(
        self, st_stubs, cuda: bool, expected: str
    ) -> None:
        st_stubs.cuda.is_available = lambda: cuda
        await st_adapter().embed_query("x")
        assert st_stubs.instances[0].device == expected

    async def test_an_explicit_device_wins(self, st_stubs) -> None:
        st_stubs.cuda.is_available = lambda: True
        await st_adapter(device="cpu").embed_query("x")
        assert st_stubs.instances[0].device == "cpu"

    async def test_model_name_is_applied(self, st_stubs) -> None:
        await st_adapter(model_name="my/model").embed_query("x")
        assert st_stubs.instances[0].name == "my/model"

    async def test_vectors_are_normalised_by_the_model_call(self, st_stubs) -> None:
        await st_adapter().embed_query("x")
        assert st_stubs.instances[0].encode_calls[0]["normalize_embeddings"] is True

    async def test_model_dimension_is_projected_to_the_database_dimension(self, st_stubs) -> None:
        vectors = await st_adapter().embed_documents(["a", "b"])
        assert {len(v) for v in vectors} == {DIM}

    async def test_encoding_runs_off_the_event_loop_thread(self, st_stubs) -> None:
        await st_adapter().embed_query("x")
        assert st_stubs.instances[0].threads[0] != threading.get_ident()

    async def test_event_loop_stays_responsive_while_encoding(self, st_stubs) -> None:
        import time

        original = StubSentenceTransformer.encode

        def slow_encode(self, texts, **kw):  # type: ignore[no-untyped-def]
            time.sleep(0.3)
            return original(self, texts, **kw)

        StubSentenceTransformer.encode = slow_encode  # type: ignore[method-assign]
        try:
            ticks = 0

            async def heartbeat() -> None:
                nonlocal ticks
                while True:
                    await asyncio.sleep(0.02)
                    ticks += 1

            task = asyncio.create_task(heartbeat())
            await st_adapter().embed_query("x")
            task.cancel()
        finally:
            StubSentenceTransformer.encode = original  # type: ignore[method-assign]
        assert ticks >= 5, "the loop was blocked by CPU-bound encoding"

    async def test_missing_ml_extras_give_an_actionable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "sentence_transformers", None)
        with pytest.raises(ImportError, match=r"\.\[ml\]"):
            await st_adapter().embed_query("x")

    async def test_langchain_bridge_is_usable_from_async_code(self, st_stubs) -> None:
        bridge = st_adapter().as_langchain_embeddings()
        vector = await bridge.aembed_query("x")
        assert len(vector) == DIM

    @defect("DEFECT-29")
    async def test_batch_size_follows_the_embedding_batch_size_setting(self, st_stubs) -> None:
        adapter = SentenceTransformersEmbeddingAdapter(
            settings=make_settings(EMBEDDING_DIMENSION=DIM, EMBEDDING_BATCH_SIZE=5)
        )
        await adapter.embed_documents(["a", "b"])
        assert st_stubs.instances[0].encode_calls[0]["batch_size"] == 5
