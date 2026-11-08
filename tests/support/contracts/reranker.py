"""Contract for ``Reranker`` adapters. Candidates are built from plain fields so every adapter can be
tested with the same inputs; each adapter's ``rerank`` returns objects with ``chunk_id`` and ``score``."""

from __future__ import annotations

import pytest
from fakes.reranker import FakeCandidate


def candidates() -> list[FakeCandidate]:
    return [
        FakeCandidate("c1", "billing invoice for the enterprise plan"),
        FakeCandidate("c2", "how to rotate a service account key"),
        FakeCandidate("c3", "invoice history and billing email changes"),
        FakeCandidate("c4", "unrelated text about gardening"),
    ]


class RerankerContract:
    @pytest.fixture
    def reranker(self):  # type: ignore[no-untyped-def]  # pragma: no cover - overridden
        raise NotImplementedError

    async def test_has_a_name(self, reranker) -> None:  # type: ignore[no-untyped-def]
        assert isinstance(reranker.name, str) and reranker.name

    async def test_returns_every_candidate_when_top_n_is_large(self, reranker) -> None:  # type: ignore[no-untyped-def]
        results = await reranker.rerank("billing invoice", candidates(), top_n=10)
        assert sorted(r.chunk_id for r in results) == ["c1", "c2", "c3", "c4"]

    async def test_top_n_limits_the_result(self, reranker) -> None:  # type: ignore[no-untyped-def]
        results = await reranker.rerank("billing invoice", candidates(), top_n=2)
        assert len(results) == 2

    async def test_scores_are_sorted_descending(self, reranker) -> None:  # type: ignore[no-untyped-def]
        results = await reranker.rerank("billing invoice", candidates(), top_n=4)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_results_only_name_input_candidates_without_duplicates(self, reranker) -> None:  # type: ignore[no-untyped-def]
        ids = [r.chunk_id for r in await reranker.rerank("billing", candidates(), top_n=10)]
        assert set(ids) <= {"c1", "c2", "c3", "c4"} and len(ids) == len(set(ids))

    async def test_empty_candidates_give_empty_results(self, reranker) -> None:  # type: ignore[no-untyped-def]
        assert await reranker.rerank("billing", [], top_n=5) == []

    async def test_zero_top_n_gives_no_results(self, reranker) -> None:  # type: ignore[no-untyped-def]
        assert await reranker.rerank("billing", candidates(), top_n=0) == []

    async def test_the_input_list_is_not_mutated(self, reranker) -> None:  # type: ignore[no-untyped-def]
        inputs = candidates()
        before = list(inputs)
        await reranker.rerank("billing invoice", inputs, top_n=3)
        assert inputs == before

    async def test_the_same_input_gives_the_same_order(self, reranker) -> None:  # type: ignore[no-untyped-def]
        first = [
            r.chunk_id for r in await reranker.rerank("billing invoice", candidates(), top_n=4)
        ]
        second = [
            r.chunk_id for r in await reranker.rerank("billing invoice", candidates(), top_n=4)
        ]
        assert first == second
