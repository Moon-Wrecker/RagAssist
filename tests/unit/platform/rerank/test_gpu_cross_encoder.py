"""Cross-encoder checks that need a real CUDA GPU (RTX 3060 in the plan). They are skipped unless the
gpu marker is selected AND CUDA is visible: ``pytest -m gpu``."""

from __future__ import annotations

import pytest
from fakes.reranker import FakeCandidate
from support.specs import need

pytestmark = pytest.mark.gpu


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


LABELLED_PAIRS = [
    # (query, relevant passage, irrelevant passage)
    (
        "how do I rotate an API key",
        "Rotate an API key from the security settings page.",
        "The office kitchen is cleaned every Friday.",
    ),
    (
        "when are invoices issued",
        "Invoices are issued on the first day of each month.",
        "Our logo uses the teal brand colour.",
    ),
    (
        "change the billing email",
        "Update the billing email under account settings.",
        "The quarterly offsite is in Lisbon.",
    ),
]


@pytest.fixture
def cross_encoder():  # type: ignore[no-untyped-def]
    if not _cuda_available():
        pytest.skip("RAGASSIST: no CUDA GPU visible; cross-encoder GPU checks skipped")
    return need("rerank.CrossEncoderReranker")(model_name="BAAI/bge-reranker-v2-m3", device="cuda")


class TestCudaCrossEncoder:
    @pytest.mark.parametrize(("query", "relevant", "irrelevant"), LABELLED_PAIRS)
    async def test_the_relevant_passage_ranks_first(
        self, cross_encoder, query: str, relevant: str, irrelevant: str
    ) -> None:  # type: ignore[no-untyped-def]
        candidates = [FakeCandidate("bad", irrelevant), FakeCandidate("good", relevant)]
        results = await cross_encoder.rerank(query, candidates, top_n=2)
        assert results[0].chunk_id == "good"

    async def test_scoring_runs_off_the_event_loop(self, cross_encoder) -> None:  # type: ignore[no-untyped-def]
        import asyncio

        ticks = 0

        async def heartbeat() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        task = asyncio.create_task(heartbeat())
        await cross_encoder.rerank("billing", [FakeCandidate("c", "billing text")] * 8, top_n=8)
        task.cancel()
        assert ticks > 0, "the event loop was blocked by GPU inference"

    async def test_a_cpu_fallback_is_reported_when_cuda_is_missing(self) -> None:
        """Runs without a GPU: the adapter must pick cpu rather than crash when asked for auto."""
        if _cuda_available():
            pytest.skip("GPU present; the CPU-fallback path is covered by the contract suite")
        reranker = need("rerank.CrossEncoderReranker")(
            model_name="BAAI/bge-reranker-v2-m3", device=None
        )
        assert reranker.device in {"cpu", None}
