"""Cross-Encoder Reranker adapter using sentence-transformers."""

from typing import Any
from ragassist.platform.rerank.ports import Candidate, Scored
from ragassist.shared.resilience import run_cpu_bound

try:
    import sentence_transformers
    from sentence_transformers import CrossEncoder
except ImportError:
    sentence_transformers = None
    CrossEncoder = None


class CrossEncoderReranker:
    """Reranker using deep Cross-Encoder models with GPU/CPU support."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str | None = None,
    ) -> None:
        if CrossEncoder is None:
            raise ImportError(
                "sentence-transformers is not installed. Install with 'pip install sentence-transformers'."
            )
        self.model_name = model_name
        if device is None:
            try:
                import torch
                self.device: str | None = "cuda" if torch.cuda.is_available() else "cpu"
            except (ImportError, Exception):
                self.device = "cpu"
        else:
            self.device = device
        self._model: Any = None

    @property
    def name(self) -> str:
        return "cross_encoder"

    def _get_model(self) -> Any:
        if self._model is None:
            self._model = CrossEncoder(self.model_name, device=self.device)
        return self._model

    def _sync_rerank(self, query: str, candidates: list[Candidate], top_n: int) -> list[Scored]:
        model = self._get_model()
        pairs = [[query, c.text] for c in candidates]
        raw_scores = model.predict(pairs)

        scored = [
            Scored(chunk_id=c.chunk_id, score=float(s))
            for c, s in zip(candidates, raw_scores, strict=True)
        ]
        scored.sort(key=lambda item: -item.score)
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


__all__ = ["CrossEncoderReranker"]
