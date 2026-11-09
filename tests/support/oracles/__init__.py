"""Reference implementations used as oracles.

They are deliberately naive, written straight from the definitions, so production code can be
compared against them. ``tests/selfcheck/test_oracles.py`` checks the oracles against values worked
out by hand, which is what makes comparing production code to them meaningful.
"""

from support.oracles.calibration import brier_score, expected_calibration_error
from support.oracles.ranking import mean_reciprocal_rank, ndcg_at_k, recall_at_k, rrf, same_ranking

__all__ = [
    "brier_score",
    "expected_calibration_error",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "recall_at_k",
    "rrf",
    "same_ranking",
]
