"""Retrieval evaluation metrics (Hit@k, Recall@k, MRR@k, nDCG@k).

Goal: Provide mathematically sound, unit-tested information retrieval metrics for evaluating
sparse, dense, and hybrid search pipelines in RAG.

Consulted references:
- Manning, Raghavan, Schütze: Introduction to Information Retrieval (Cambridge University Press)
- RAGAS (Retrieval Augmented Generation Assessment) evaluation framework
- TREC evaluation procedures and NDCG discounting formulations
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def hit_at_k(retrieved: Sequence[str], relevant: Sequence[str] | set[str], k: int = 5) -> float:
    """Computes Hit Rate @ K: 1.0 if at least one relevant item is in the top-k, else 0.0."""
    if not relevant or not retrieved:
        return 0.0
    top_k = retrieved[:k]
    relevant_set = set(relevant)
    return 1.0 if any(item in relevant_set for item in top_k) else 0.0


def recall_at_k(retrieved: Sequence[str], relevant: Sequence[str] | set[str], k: int = 5) -> float:
    """Computes Recall @ K: proportion of relevant items retrieved in top-k."""
    if not relevant:
        return 0.0
    top_k = retrieved[:k]
    relevant_set = set(relevant)
    hits = sum(1 for item in top_k if item in relevant_set)
    return float(hits) / float(len(relevant_set))


def mrr_at_k(retrieved: Sequence[str], relevant: Sequence[str] | set[str], k: int = 5) -> float:
    """Computes Mean Reciprocal Rank (MRR) @ K: 1 / rank of the first relevant item (1-indexed)."""
    if not relevant or not retrieved:
        return 0.0
    relevant_set = set(relevant)
    for rank, item in enumerate(retrieved[:k], start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(
    runs: Sequence[tuple[Sequence[str], Sequence[str] | set[str]]],
) -> float:
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


def ndcg_at_k(
    retrieved: Sequence[str],
    relevant: Sequence[str] | Mapping[str, float] | set[str],
    k: int = 5,
) -> float:
    """Computes Normalized Discounted Cumulative Gain (nDCG) @ K with binary or graded relevance."""
    if not relevant or not retrieved:
        return 0.0

    if isinstance(relevant, Mapping):
        top_k = retrieved[:k]
        dcg = sum(
            relevant.get(item, 0.0) / math.log2(rank + 1)
            for rank, item in enumerate(top_k, start=1)
        )
        ideal = sorted(relevant.values(), reverse=True)[:k]
        idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
        return 0.0 if idcg == 0.0 else dcg / idcg

    relevant_set = set(relevant)
    top_k = retrieved[:k]

    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, item in enumerate(top_k, start=1)
        if item in relevant_set
    )
    ideal_hits = min(len(relevant_set), k)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))

    return dcg / idcg if idcg > 0.0 else 0.0
