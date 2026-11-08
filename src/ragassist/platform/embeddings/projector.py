"""Vector projection utilities for aligning embeddings to database dimension constraints."""

import math
from collections.abc import Sequence


class DimensionProjector:
    """Projects embedding vectors to a target dimensionality while preserving normalization."""

    def __init__(self, target_dimension: int = 1536) -> None:
        self.target_dimension = target_dimension

    def project_vector(self, vec: Sequence[float]) -> list[float]:
        """Project a single vector to target_dimension."""
        curr_dim = len(vec)
        if curr_dim == self.target_dimension:
            return list(vec)

        if curr_dim < self.target_dimension:
            # Zero-padding: preserve norm and angular relationships
            padded = list(vec) + [0.0] * (self.target_dimension - curr_dim)
            return self._normalize(padded)

        # Truncation (Matryoshka Representation): slice and re-normalize
        truncated = list(vec[: self.target_dimension])
        return self._normalize(truncated)

    def project_vectors(self, vectors: Sequence[Sequence[float]]) -> list[list[float]]:
        """Project a batch of vectors."""
        return [self.project_vector(v) for v in vectors]

    @staticmethod
    def _normalize(vec: list[float]) -> list[float]:
        norm = math.sqrt(sum(x * x for x in vec))
        if norm < 1e-12:
            return vec
        return [x / norm for x in vec]
