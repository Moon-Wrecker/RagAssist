"""The evaluation metrics (evals/metrics) against the oracles, plus hand-computed spot values. The
offline eval harness is only as trustworthy as these numbers."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from support.oracles import (
    brier_score,
    expected_calibration_error,
    mean_reciprocal_rank,
    ndcg_at_k,
    recall_at_k,
)
from support.specs import need

ids = st.sampled_from([f"d{i}" for i in range(10)])
ranked_lists = st.lists(ids, min_size=0, max_size=8, unique=True)
probabilities = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


class TestRetrievalMetricsSpotValues:
    def test_recall_at_three_of_four_relevant_in_the_top_three(self) -> None:
        assert need("eval.recall_at_k")(["a", "b", "c", "d"], {"a", "c", "x"}, 3) == pytest.approx(
            2 / 3
        )

    def test_mrr_of_a_hit_in_second_place(self) -> None:
        runs = [(["a", "b"], {"b"})]
        assert need("eval.mean_reciprocal_rank")(runs) == pytest.approx(0.5)

    def test_ndcg_of_the_ideal_order_is_one(self) -> None:
        assert need("eval.ndcg_at_k")(["a", "c"], {"a": 3, "c": 2}, 2) == pytest.approx(1.0)


class TestRetrievalMetricsAgainstOracles:
    @settings(max_examples=150, deadline=None)
    @given(ranked_lists, st.frozensets(ids, max_size=6), st.integers(min_value=1, max_value=10))
    def test_recall_matches_the_oracle(
        self, ranked: list[str], relevant: frozenset[str], k: int
    ) -> None:
        assert need("eval.recall_at_k")(ranked, relevant, k) == pytest.approx(
            recall_at_k(ranked, relevant, k)
        )

    @settings(max_examples=150, deadline=None)
    @given(
        st.lists(st.tuples(ranked_lists, st.frozensets(ids, max_size=4)), min_size=0, max_size=5)
    )
    def test_mrr_matches_the_oracle(self, runs) -> None:  # type: ignore[no-untyped-def]
        assert need("eval.mean_reciprocal_rank")(runs) == pytest.approx(mean_reciprocal_rank(runs))

    @settings(max_examples=150, deadline=None)
    @given(
        ranked_lists,
        st.dictionaries(ids, st.floats(min_value=0, max_value=3), max_size=8),
        st.integers(min_value=1, max_value=10),
    )
    def test_ndcg_matches_the_oracle(self, ranked, gains, k: int) -> None:  # type: ignore[no-untyped-def]
        assert need("eval.ndcg_at_k")(ranked, gains, k) == pytest.approx(
            ndcg_at_k(ranked, gains, k)
        )


class TestCalibrationAgainstOracles:
    @settings(max_examples=150, deadline=None)
    @given(
        st.lists(
            st.tuples(probabilities, st.integers(min_value=0, max_value=1)), min_size=1, max_size=40
        )
    )
    def test_brier_matches_the_oracle(self, pairs) -> None:  # type: ignore[no-untyped-def]
        probs, outcomes = zip(*pairs, strict=True)
        assert need("eval.brier_score")(list(probs), list(outcomes)) == pytest.approx(
            brier_score(probs, outcomes)
        )

    @settings(max_examples=150, deadline=None)
    @given(
        st.lists(
            st.tuples(probabilities, st.integers(min_value=0, max_value=1)), min_size=1, max_size=40
        ),
        st.integers(min_value=1, max_value=20),
    )
    def test_ece_matches_the_oracle(self, pairs, bins: int) -> None:  # type: ignore[no-untyped-def]
        probs, outcomes = zip(*pairs, strict=True)
        expected = expected_calibration_error(probs, outcomes, bins=bins)
        assert need("eval.expected_calibration_error")(
            list(probs), list(outcomes), bins=bins
        ) == pytest.approx(expected)

    def test_perfect_forecasts_score_zero(self) -> None:
        assert need("eval.brier_score")([1.0, 0.0], [1, 0]) == 0.0
        assert need("eval.expected_calibration_error")([1.0, 0.0], [1, 0]) == 0.0
