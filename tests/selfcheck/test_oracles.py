"""The oracles are the yardstick for production metrics, so they are checked against values worked
out by hand (not by running the oracle again)."""

from __future__ import annotations

import math

import pytest
from support.oracles import (
    brier_score,
    expected_calibration_error,
    mean_reciprocal_rank,
    ndcg_at_k,
    recall_at_k,
    rrf,
    same_ranking,
)

pytestmark = pytest.mark.selfcheck


class TestReciprocalRankFusionByHand:
    def test_two_rankings_with_one_shared_order(self) -> None:
        # a: 1/61 + 1/62, b: 1/62 + 1/61 (a tie, broken by first appearance: a), c: 1/63, d: 1/63 (tie: c)
        result = rrf([["a", "b", "c"], ["b", "a", "d"]], k=60)
        assert [item for item, _ in result] == ["a", "b", "c", "d"]
        assert result[0][1] == pytest.approx(1 / 61 + 1 / 62)
        assert result[2][1] == pytest.approx(1 / 63)

    def test_a_single_ranking_keeps_its_order(self) -> None:
        assert [item for item, _ in rrf([["x", "y", "z"]], k=60)] == ["x", "y", "z"]

    def test_disjoint_rankings_interleave_by_rank(self) -> None:
        assert [item for item, _ in rrf([["a", "b"], ["c", "d"]], k=60)] == ["a", "c", "b", "d"]

    def test_an_item_ranked_first_twice_scores_twice(self) -> None:
        result = dict(rrf([["a", "b"], ["a", "c"]], k=60))
        assert result["a"] == pytest.approx(2 / 61)

    def test_duplicates_inside_one_ranking_count_at_their_best_rank_only(self) -> None:
        result = dict(rrf([["a", "a", "b"]], k=60))
        assert result["a"] == pytest.approx(1 / 61)
        assert result["b"] == pytest.approx(1 / 63)

    def test_empty_inputs_give_empty_output(self) -> None:
        assert rrf([], k=60) == []
        assert rrf([[]], k=60) == []

    def test_a_larger_k_flattens_the_scores(self) -> None:
        small = dict(rrf([["a", "b"]], k=1))
        large = dict(rrf([["a", "b"]], k=1000))
        assert (small["a"] - small["b"]) > (large["a"] - large["b"])


class TestRetrievalMetricsByHand:
    def test_recall_at_k_counts_relevant_items_in_the_top_k(self) -> None:
        ranked = ["a", "b", "c", "d"]
        assert recall_at_k(ranked, {"a", "c", "x"}, 3) == pytest.approx(2 / 3)
        assert recall_at_k(ranked, {"a", "c", "x"}, 1) == pytest.approx(1 / 3)

    def test_recall_is_zero_when_nothing_is_relevant(self) -> None:
        assert recall_at_k(["a"], set(), 5) == 0.0

    def test_mean_reciprocal_rank_averages_the_first_hit(self) -> None:
        runs = [(["a", "b"], {"b"}), (["c", "d"], {"x"})]  # 1/2 and 0
        assert mean_reciprocal_rank(runs) == pytest.approx(0.25)

    def test_mean_reciprocal_rank_of_no_runs_is_zero(self) -> None:
        assert mean_reciprocal_rank([]) == 0.0

    def test_ndcg_is_one_for_the_ideal_order(self) -> None:
        assert ndcg_at_k(["a", "c"], {"a": 3, "c": 2}, 2) == pytest.approx(1.0)

    def test_ndcg_is_below_one_for_a_reversed_order(self) -> None:
        value = ndcg_at_k(["c", "a"], {"a": 3, "c": 2}, 2)
        dcg = 2 + 3 / math.log2(3)
        idcg = 3 + 2 / math.log2(3)
        assert value == pytest.approx(dcg / idcg)
        assert value < 1.0

    def test_ndcg_is_zero_without_gains(self) -> None:
        assert ndcg_at_k(["a"], {}, 3) == 0.0


class TestCalibrationByHand:
    def test_brier_is_zero_for_perfect_predictions(self) -> None:
        assert brier_score([1.0, 0.0], [1, 0]) == 0.0

    def test_brier_of_an_uninformative_forecast_is_a_quarter(self) -> None:
        assert brier_score([0.5, 0.5], [1, 0]) == pytest.approx(0.25)

    def test_brier_rejects_mismatched_lengths(self) -> None:
        with pytest.raises(ValueError):
            brier_score([0.5], [1, 0])

    def test_ece_is_zero_when_confidence_matches_accuracy(self) -> None:
        assert expected_calibration_error([0.0] * 5, [0] * 5) == 0.0

    def test_ece_of_overconfident_top_bin(self) -> None:
        # four predictions of 1.0 in the last bin, three of them right: |1.0 - 0.75| = 0.25
        assert expected_calibration_error([1.0] * 4, [1, 1, 1, 0]) == pytest.approx(0.25)

    def test_ece_of_a_slightly_overconfident_bin(self) -> None:
        assert expected_calibration_error([0.9] * 10, [1] * 10) == pytest.approx(0.1)

    def test_ece_of_nothing_is_zero(self) -> None:
        assert expected_calibration_error([], []) == 0.0


class TestSameRanking:
    def test_identical_rankings_match(self) -> None:
        assert same_ranking([("a", 0.5), ("b", 0.2)], [("a", 0.5), ("b", 0.2)])

    def test_a_different_order_with_clearly_different_scores_does_not_match(self) -> None:
        assert not same_ranking([("b", 0.2), ("a", 0.5)], [("a", 0.5), ("b", 0.2)])

    def test_scores_outside_tolerance_do_not_match(self) -> None:
        assert not same_ranking([("a", 0.5)], [("a", 0.6)])
