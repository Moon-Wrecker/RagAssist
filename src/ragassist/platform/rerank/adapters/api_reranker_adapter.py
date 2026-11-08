"""API-based Reranker adapter (e.g., Cohere, Jina, or standard rerank API)."""

from typing import Any
import httpx
from ragassist.platform.rerank.ports import Candidate, Scored


class ApiReranker:
    """Reranks candidates via an external HTTP rerank endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._http = http

    @property
    def name(self) -> str:
        return "api"

    async def rerank(
        self,
        query: str,
        candidates: list[Candidate],
        *,
        top_n: int,
    ) -> list[Scored]:
        if top_n <= 0 or not candidates:
            return []

        payload = {
            "model": self.model,
            "query": query,
            "documents": [c.text for c in candidates],
            "top_n": top_n,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/rerank"

        if self._http is not None:
            res = await self._http.post(url, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json=payload, headers=headers)

        res.raise_for_status()
        data: dict[str, Any] = res.json()
        results = data.get("results", [])

        scored: list[Scored] = []
        for item in results:
            idx = item.get("index")
            if idx is not None and 0 <= idx < len(candidates):
                score_val = float(item.get("relevance_score", item.get("score", 0.0)))
                scored.append(Scored(chunk_id=candidates[idx].chunk_id, score=score_val))

        scored.sort(key=lambda item: -item.score)
        return scored[:top_n]


__all__ = ["ApiReranker"]
