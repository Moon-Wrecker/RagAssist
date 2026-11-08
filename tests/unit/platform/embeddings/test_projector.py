"""DimensionProjector: pure maths, so table-driven plus property-based."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ragassist.platform.embeddings.projector import DimensionProjector

finite = st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False)


def norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / (norm(a) * norm(b))


class TestProjection:
    def test_matching_dimension_is_returned_unchanged(self) -> None:
        assert DimensionProjector(3).project_vector([0.1, 0.2, 0.3]) == [0.1, 0.2, 0.3]

    def test_matching_dimension_returns_a_copy(self) -> None:
        source = [1.0, 2.0]
        out = DimensionProjector(2).project_vector(source)
        out[0] = 99.0
        assert source == [1.0, 2.0]

    def test_shorter_vectors_are_zero_padded_then_normalised(self) -> None:
        out = DimensionProjector(4).project_vector([3.0, 4.0])
        assert out == pytest.approx([0.6, 0.8, 0.0, 0.0])

    def test_longer_vectors_are_truncated_then_normalised(self) -> None:
        out = DimensionProjector(2).project_vector([3.0, 4.0, 12.0, 5.0])
        assert out == pytest.approx([0.6, 0.8])

    def test_zero_vector_stays_finite(self) -> None:
        out = DimensionProjector(4).project_vector([0.0, 0.0])
        assert out == [0.0] * 4 and all(math.isfinite(x) for x in out)

    def test_empty_vector_pads_to_zeros(self) -> None:
        assert DimensionProjector(3).project_vector([]) == [0.0, 0.0, 0.0]

    def test_batch_projection_preserves_count_and_order(self) -> None:
        out = DimensionProjector(2).project_vectors(
            [[1.0, 0.0, 9.0], [0.0, 1.0, 9.0], [3.0, 4.0, 0.0]]
        )
        assert len(out) == 3
        for got, expected in zip(out, [[1.0, 0.0], [0.0, 1.0], [0.6, 0.8]], strict=True):
            assert got == pytest.approx(expected)

    def test_empty_batch(self) -> None:
        assert DimensionProjector(2).project_vectors([]) == []

    def test_accepts_any_sequence(self) -> None:
        assert DimensionProjector(2).project_vector((3.0, 4.0, 0.0)) == pytest.approx([0.6, 0.8])

    def test_default_target_matches_the_pgvector_column(self) -> None:
        assert DimensionProjector().target_dimension == 1536


class TestProperties:
    @given(st.lists(finite, min_size=1, max_size=40), st.integers(min_value=1, max_value=60))
    def test_output_always_has_the_target_length(self, vec: list[float], target: int) -> None:
        assert len(DimensionProjector(target).project_vector(vec)) == target

    @given(st.lists(finite, min_size=1, max_size=20), st.integers(min_value=21, max_value=60))
    def test_padding_is_unit_length_and_keeps_direction(
        self, vec: list[float], target: int
    ) -> None:
        if norm(vec) < 1e-6:
            return
        out = DimensionProjector(target).project_vector(vec)
        assert norm(out) == pytest.approx(1.0, abs=1e-9)
        assert cosine(out[: len(vec)], vec) == pytest.approx(1.0, abs=1e-9)

    @given(st.lists(finite, min_size=5, max_size=40), st.integers(min_value=1, max_value=4))
    def test_truncation_is_unit_length_or_zero(self, vec: list[float], target: int) -> None:
        out = DimensionProjector(target).project_vector(vec)
        assert norm(out) == pytest.approx(1.0, abs=1e-9) or norm(out) < 1e-6

    @given(st.lists(finite, min_size=1, max_size=30), st.integers(min_value=1, max_value=60))
    def test_projection_is_idempotent(self, vec: list[float], target: int) -> None:
        projector = DimensionProjector(target)
        once = projector.project_vector(vec)
        assert projector.project_vector(once) == once
