"""FlashRank ONNX Reranker adapter."""

from typing import Any
from ragassist.platform.rerank.ports import Candidate, Scored
from ragassist.shared.resilience import run_cpu_bound

try:
    import flashrank
    from flashrank import Ranker, RerankRequest
except ImportError:
    flashrank = None
    Ranker = None
    RerankRequest = None


class FlashRankReranker:
    """Lightweight CPU-based reranker using FlashRank ONNX models."""

    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2") -> None:
        if Ranker is None:
            raise ImportError(
                "flashrank is not installed. Install with 'pip install flashrank'."
            )
        self.model_name = model_name
        self._ranker: Any = None

    @property
    def name(self) -> str:
        return "flashrank"

    def _get_ranker(self) -> Any:
        if self._ranker is None:
            self._ranker = Ranker(model_name=self.model_name)
        return self._ranker

    def _sync_rerank(self, query: str, candidates: list[Candidate], top_n: int) -> list[Scored]:
        ranker = self._get_ranker()
        passages = [{"id": c.chunk_id, "text": c.text} for c in candidates]
        request = RerankRequest(query=query, passages=passages)
        results = ranker.rerank(request)

        scored = [
            Scored(chunk_id=str(r["id"]), score=float(r["score"]))
            for r in results
        ]
        scored.sort(key=lambda s: -s.score)
        return scored[:top_n]

    async def rerank(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        top_n: int,
    ) -> list[Scored]:
        if top_n <= 0 or not candidates:
            return []

        return await run_cpu_bound(self._sync_rerank, query, candidates, top_n)


__all__ = ["FlashRankReranker"]
