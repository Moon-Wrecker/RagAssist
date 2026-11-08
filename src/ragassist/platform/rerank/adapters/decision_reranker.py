"""Decision-layer reranker scoring candidates via Decider port."""

from typing import Any
from ragassist.platform.decisions.ports import ScoreLevel, ScoreQuestion
from ragassist.platform.rerank.ports import Candidate, Scored


class DecisionReranker:
    """Reranker that uses a decision engine to evaluate candidate relevance."""

    def __init__(self, decider: Any) -> None:
        self.decider = decider

    @property
    def name(self) -> str:
        return "decision"

    async def rerank(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        top_n: int,
    ) -> list[Scored]:
        if top_n <= 0 or not candidates:
            return []

        levels = [
            ScoreLevel(value=0, label="irrelevant"),
            ScoreLevel(value=1, label="relevant"),
        ]
        question = ScoreQuestion(name="relevance", instructions=query, levels=levels)
        scored: list[Scored] = []
        for c in candidates:
            ans = await self.decider.evaluate_score(input_text=c.text, question=question)
            scored.append(Scored(chunk_id=c.chunk_id, score=float(ans.score)))

        scored.sort(key=lambda item: -item.score)
        return scored[:top_n]


__all__ = ["DecisionReranker"]
