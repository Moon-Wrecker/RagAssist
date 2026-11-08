"""In-memory vector store with strict tenant isolation (cosine similarity).

Global documents (``tenant_id=None``) are visible to every tenant, matching the data-model plan.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch: {len(a)} vs {len(b)}")
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (norm_a * norm_b)


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.chunks: list[dict[str, Any]] = []

    def add_chunk(
        self,
        chunk_id: UUID,
        document_id: UUID,
        tenant_id: UUID | None,
        content: str,
        embedding: list[float],
        heading_path: str = "",
        page_number: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.chunks.append(
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "tenant_id": tenant_id,
                "content": content,
                "embedding": embedding,
                "heading_path": heading_path,
                "page_number": page_number,
                "metadata": metadata or {},
            }
        )

    def search(
        self, tenant_id: UUID, query_embedding: list[float], top_k: int = 6
    ) -> list[dict[str, Any]]:
        visible = [c for c in self.chunks if c["tenant_id"] in (tenant_id, None)]
        scored = [
            {**c, "score": cosine_similarity(query_embedding, c["embedding"])} for c in visible
        ]
        scored.sort(key=lambda c: c["score"], reverse=True)
        return scored[:top_k]
