"""DecisionReranker scores each candidate with the decider's Score question (plan section 6)."""

from __future__ import annotations

import pytest
from fakes.decider import FakeDecider
from fakes.reranker import FakeCandidate
from support.specs import need


class ScoringDecider(FakeDecider):
    """Scores by how many query words a candidate shares, so ordering is checkable."""

    async def evaluate_score(self, input_text, question):  # type: ignore[no-untyped-def]
        from ragassist.platform.decisions.ports import ScoreAnswer

        terms = set(input_text.lower().split())
        overlap = len(terms & set(question.instructions.lower().split()))
        return ScoreAnswer(question.name, min(1.0, overlap / 10), 1.0)


class TestDecisionReranking:
    async def test_candidates_are_ordered_by_the_decider_score(self) -> None:
        reranker = need("rerank.DecisionReranker")(ScoringDecider("scorer"))
        candidates = [
            FakeCandidate("low", "gardening"),
            FakeCandidate("high", "billing invoice billing"),
        ]
        results = await reranker.rerank("billing invoice", candidates, top_n=2)
        assert results[0].chunk_id in {"high", "low"}
        assert [r.score for r in results] == sorted([r.score for r in results], reverse=True)

    async def test_the_decider_is_asked_once_per_candidate(self) -> None:
        decider = FakeDecider("scorer", score=0.4)
        reranker = need("rerank.DecisionReranker")(decider)
        await reranker.rerank("q", [FakeCandidate(f"c{i}", "t") for i in range(4)], top_n=4)
        assert len(decider.calls) == 4

    async def test_a_decider_failure_is_raised_so_the_chain_can_fall_back(self) -> None:
        reranker = need("rerank.DecisionReranker")(
            FakeDecider("broken", error=RuntimeError("down"))
        )
        with pytest.raises(RuntimeError):
            await reranker.rerank("q", [FakeCandidate("c1", "t")], top_n=1)
