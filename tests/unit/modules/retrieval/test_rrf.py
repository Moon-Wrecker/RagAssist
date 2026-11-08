"""Reciprocal rank fusion (ADR 0003 / plan section 3, RETRIEVAL_RRF_K): checked against the oracle and
against properties that must hold for any input."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from support.oracles import rrf, same_ranking
from support.specs import need

pytestmark = pytest.mark.slow

ids = st.sampled_from([f"c{i}" for i in range(12)])
rankings_strategy = st.lists(st.lists(ids, min_size=0, max_size=10), min_size=0, max_size=4)


def fuse(rankings, k: int = 60):  # type: ignore[no-untyped-def]
    return need("retrieval.reciprocal_rank_fusion")(rankings, k=k)


class TestWorkedExamples:
    def test_the_documented_two_list_example(self) -> None:
        # a: 1/61 + 1/62, b: 1/62 + 1/61 (tie, a first), c: 1/63, d: 1/63 (tie, c first)
        result = fuse([["a", "b", "c"], ["b", "a", "d"]], k=60)
        assert [item for item, _ in result] == ["a", "b", "c", "d"]
        assert result[0][1] == pytest.approx(1 / 61 + 1 / 62)

    def test_a_single_list_keeps_its_order(self) -> None:
        assert [item for item, _ in fuse([["x", "y", "z"]])] == ["x", "y", "z"]

    def test_identical_lists_double_each_score_and_keep_the_order(self) -> None:
        result = fuse([["a", "b"], ["a", "b"]], k=60)
        assert [item for item, _ in result] == ["a", "b"]
        assert result[0][1] == pytest.approx(2 / 61)

    def test_disjoint_lists_interleave_by_rank(self) -> None:
        assert [item for item, _ in fuse([["a", "b"], ["c", "d"]])] == ["a", "c", "b", "d"]

    def test_duplicates_inside_one_list_count_at_their_best_rank(self) -> None:
        result = dict(fuse([["a", "a", "b"]], k=60))
        assert result["a"] == pytest.approx(1 / 61)

    def test_empty_inputs_give_an_empty_result(self) -> None:
        assert fuse([]) == []
        assert fuse([[]]) == []

    def test_a_larger_k_flattens_the_gap_between_ranks(self) -> None:
        small = dict(fuse([["a", "b"]], k=1))
        large = dict(fuse([["a", "b"]], k=1000))
        assert small["a"] - small["b"] > large["a"] - large["b"]


class TestAgainstTheOracle:
    @settings(max_examples=150, deadline=None)
    @given(rankings_strategy, st.integers(min_value=1, max_value=100))
    def test_production_matches_the_oracle(self, rankings: list[list[str]], k: int) -> None:
        assert same_ranking(fuse(rankings, k), rrf(rankings, k))


class TestProperties:
    @settings(max_examples=150, deadline=None)
    @given(rankings_strategy)
    def test_the_output_is_exactly_the_union_of_the_inputs(self, rankings: list[list[str]]) -> None:
        output = {item for item, _ in fuse(rankings)}
        assert output == {item for ranking in rankings for item in ranking}

    @settings(max_examples=150, deadline=None)
    @given(rankings_strategy)
    def test_scores_are_sorted_descending(self, rankings: list[list[str]]) -> None:
        scores = [score for _, score in fuse(rankings)]
        assert scores == sorted(scores, reverse=True)

    @settings(max_examples=150, deadline=None)
    @given(rankings_strategy)
    def test_the_multiset_of_scores_ignores_the_order_of_the_lists(
        self, rankings: list[list[str]]
    ) -> None:
        forward = sorted(score for _, score in fuse(rankings))
        backward = sorted(score for _, score in fuse(list(reversed(rankings))))
        assert forward == pytest.approx(backward)

    @settings(max_examples=150, deadline=None)
    @given(rankings_strategy)
    def test_no_score_is_negative_and_none_exceed_the_number_of_lists(
        self, rankings: list[list[str]]
    ) -> None:
        for _, score in fuse(rankings):
            assert 0 < score <= len(rankings) / 61 + 1e-12
