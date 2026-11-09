"""Ranking oracles: reciprocal rank fusion and retrieval metrics, from their definitions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def rrf(rankings: Sequence[Sequence[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal rank fusion. Score = sum over rankings of 1 / (k + rank), rank from 1.

    An id repeated inside one ranking counts only at its best rank. Results are sorted by score
    descending; ties are broken by first appearance across the rankings.
    """
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    counter = 0
    for ranking in rankings:
        seen_here: set[str] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen_here:
                continue
            seen_here.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            if item not in first_seen:
                first_seen[item] = counter
                counter += 1
    return sorted(scores.items(), key=lambda pair: (-pair[1], first_seen[pair[0]]))


def same_ranking(
    actual: Sequence[tuple[str, float]], expected: Sequence[tuple[str, float]], tol: float = 1e-9
) -> bool:
    """Equal ids in the same order, and scores within ``tol``. Floating-point summation order can
    reorder exact ties, so ids are only compared where the expected scores are clearly apart."""
    if [item for item, _ in actual] != [item for item, _ in expected]:
        clear = all(
            abs(a[1] - b[1]) > tol or a[0] == b[0] for a, b in zip(actual, expected, strict=False)
        )
        if not clear:
            return False
    return all(abs(a[1] - b[1]) <= tol for a, b in zip(actual, expected, strict=True))


def recall_at_k(ranked: Sequence[str], relevant: Sequence[str] | set[str], k: int) -> float:
    """Fraction of relevant items found in the top k. Zero when nothing is relevant."""
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    return len(set(ranked[:k]) & relevant_set) / len(relevant_set)


def mean_reciprocal_rank(runs: Sequence[tuple[Sequence[str], Sequence[str] | set[str]]]) -> float:
    """Mean over runs of 1 / rank of the first relevant item (rank from 1; zero when none)."""
    if not runs:
        return 0.0
    total = 0.0
    for ranked, relevant in runs:
        relevant_set = set(relevant)
        for rank, item in enumerate(ranked, start=1):
            if item in relevant_set:
                total += 1.0 / rank
                break
    return total / len(runs)


def ndcg_at_k(ranked: Sequence[str], gains: Mapping[str, float], k: int) -> float:
    """Normalised discounted cumulative gain at k, with graded relevance ``gains``."""
    dcg = sum(
        gains.get(item, 0.0) / math.log2(rank + 1) for rank, item in enumerate(ranked[:k], start=1)
    )
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
    return 0.0 if idcg == 0 else dcg / idcg
