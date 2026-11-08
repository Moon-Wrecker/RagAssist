"""Abstract ports and data contracts for reranking models."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Candidate:
    """A candidate text chunk to be reranked."""

    chunk_id: str
    text: str
    score: float = 0.0


@dataclass(frozen=True)
class Scored:
    """A candidate scored by a reranker."""

    chunk_id: str
    score: float


@dataclass(frozen=True)
class ChainResult:
    """Output of a reranker chain execution."""

    items: list[Scored]
    reranker: str


@runtime_checkable
class Reranker(Protocol):
    """Protocol for candidate rerankers."""

    @property
    def name(self) -> str:
        """Adapter name (e.g., 'cross_encoder', 'flashrank', 'api', 'decision', 'none')."""
        ...

    async def rerank(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        top_n: int,
    ) -> list[Scored]:
        """Rerank candidates against the query and return the top_n scored candidates.

        Args:
            query: The search query text.
            candidates: List of candidate chunks to rerank.
            top_n: Maximum number of scored items to return.

        Returns:
            List of Scored results sorted by score descending.
        """
        ...


__all__ = [
    "Candidate",
    "ChainResult",
    "Reranker",
    "Scored",
]
