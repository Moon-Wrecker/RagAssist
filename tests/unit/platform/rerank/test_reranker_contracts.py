"""Every reranker adapter runs the shared RerankerContract. Libraries that are not installed (FlashRank,
sentence-transformers) make their suite PENDING with the dependency named, so nothing is stubbed.
The API reranker talks HTTP, so it is mocked with respx and runs everywhere."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fakes.decider import FakeDecider
from fakes.reranker import FakeCandidate
from support.contracts import RerankerContract
from support.specs import need


class TestNoopRerankerContract(RerankerContract):
    @pytest.fixture
    def reranker(self):  # type: ignore[no-untyped-def]
        return need("rerank.NoopReranker")()


class TestDecisionRerankerContract(RerankerContract):
    @pytest.fixture
    def reranker(self):  # type: ignore[no-untyped-def]
        return need("rerank.DecisionReranker")(FakeDecider("scorer", score=0.5))


@pytest.mark.network
class TestFlashRankRerankerContract(RerankerContract):
    """Needs the flashrank package; PENDING until it is installed."""

    @pytest.fixture
    def reranker(self):  # type: ignore[no-untyped-def]
        return need("rerank.FlashRankReranker")(model_name="ms-marco-TinyBERT-L-2-v2")


class TestCrossEncoderRerankerContract(RerankerContract):
    """Needs sentence-transformers (the ml extra); the GPU-only checks live in test_gpu_cross_encoder.py."""

    @pytest.fixture
    def reranker(self):  # type: ignore[no-untyped-def]
        return need("rerank.CrossEncoderReranker")(
            model_name="BAAI/bge-reranker-v2-m3", device="cpu"
        )


def _overlap_score(query: str, document: str) -> float:
    terms = set(query.lower().split())
    return len(terms & set(document.lower().split())) / len(terms) if terms else 0.0


class TestApiRerankerContract(RerankerContract):
    """A mocked provider that scores by word overlap, so the contract is about the adapter's mapping
    of request and response, not about any particular model."""

    @pytest.fixture
    def reranker(self):  # type: ignore[no-untyped-def]
        def respond(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            scored = [
                {"index": i, "relevance_score": _overlap_score(body["query"], doc)}
                for i, doc in enumerate(body["documents"])
            ]
            scored.sort(key=lambda item: -item["relevance_score"])
            return httpx.Response(200, json={"results": scored[: body.get("top_n", len(scored))]})

        mock = respx.mock(assert_all_called=False)
        mock.start()
        mock.post("https://rerank.test/v1/rerank").mock(side_effect=respond)
        try:
            yield need("rerank.ApiReranker")(
                base_url="https://rerank.test/v1",
                api_key="test-key",
                model="rerank-x",
                http=httpx.AsyncClient(),
            )
        finally:
            mock.stop()


class TestApiRerankerWire:
    async def test_sends_the_key_as_a_bearer_token(self) -> None:
        with respx.mock(assert_all_called=True) as mock:
            route = mock.post("https://rerank.test/v1/rerank").mock(
                return_value=httpx.Response(200, json={"results": []})
            )
            reranker = need("rerank.ApiReranker")(
                base_url="https://rerank.test/v1",
                api_key="secret-key",
                model="m",
                http=httpx.AsyncClient(),
            )
            await reranker.rerank("q", [FakeCandidate("c1", "text")], top_n=1)
        assert route.calls.last.request.headers["authorization"] == "Bearer secret-key"

    async def test_sends_the_documents_in_candidate_order(self) -> None:
        with respx.mock(assert_all_called=True) as mock:
            route = mock.post("https://rerank.test/v1/rerank").mock(
                return_value=httpx.Response(200, json={"results": []})
            )
            reranker = need("rerank.ApiReranker")(
                base_url="https://rerank.test/v1", api_key="k", model="m", http=httpx.AsyncClient()
            )
            await reranker.rerank(
                "q", [FakeCandidate("c1", "alpha"), FakeCandidate("c2", "beta")], top_n=2
            )
        sent = json.loads(route.calls.last.request.content)
        assert sent["documents"] == ["alpha", "beta"] and sent["query"] == "q"

    async def test_a_provider_error_is_raised_so_the_chain_can_fall_back(self) -> None:
        with respx.mock(assert_all_called=True) as mock:
            mock.post("https://rerank.test/v1/rerank").mock(return_value=httpx.Response(503))
            reranker = need("rerank.ApiReranker")(
                base_url="https://rerank.test/v1", api_key="k", model="m", http=httpx.AsyncClient()
            )
            with pytest.raises(Exception):  # noqa: B017 - the adapter surfaces the transport error
                await reranker.rerank("q", [FakeCandidate("c1", "x")], top_n=1)
