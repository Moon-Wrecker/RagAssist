"""Calibration oracles: Brier score and expected calibration error, from their definitions."""

from __future__ import annotations

from collections.abc import Sequence


def brier_score(probs: Sequence[float], outcomes: Sequence[int]) -> float:
    """Mean squared difference between predicted probability and the 0/1 outcome. Lower is better."""
    if len(probs) != len(outcomes):
        raise ValueError("probs and outcomes must have the same length")
    if not probs:
        return 0.0
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes, strict=True)) / len(probs)


def expected_calibration_error(
    probs: Sequence[float], outcomes: Sequence[int], *, bins: int = 10
) -> float:
    """Weighted mean of |mean confidence - observed accuracy| over equal-width bins on [0, 1].

    A probability of exactly 1.0 falls in the last bin.
    """
    if len(probs) != len(outcomes):
        raise ValueError("probs and outcomes must have the same length")
    n = len(probs)
    if n == 0:
        return 0.0
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, o in zip(probs, outcomes, strict=True):
        buckets[min(int(p * bins), bins - 1)].append((p, o))
    total = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        confidence = sum(p for p, _ in bucket) / len(bucket)
        accuracy = sum(o for _, o in bucket) / len(bucket)
        total += len(bucket) / n * abs(confidence - accuracy)
    return total
