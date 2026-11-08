"""No-op reranker keeping input candidate order and scores."""

from ragassist.platform.rerank.ports import Candidate, Scored


class NoopReranker:
    """Pass-through reranker that preserves the input candidate ranking."""

    @property
    def name(self) -> str:
        return "none"

    async def rerank(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        top_n: int,
    ) -> list[Scored]:
        if top_n <= 0 or not candidates:
            return []
        return [Scored(chunk_id=c.chunk_id, score=c.score) for c in candidates[:top_n]]


__all__ = ["NoopReranker"]
