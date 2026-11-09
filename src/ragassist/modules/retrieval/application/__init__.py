"""Application use cases and services for Retrieval module."""

from typing import Any, Protocol
from ragassist.shared.domain import TenantId
from ragassist.modules.retrieval.domain import Citation, ContextPack, Hit, Passage, RetrievedChunk
from ragassist.modules.retrieval.fusion import HybridRetriever, fuse_hit_rankings


class RetrievalService(Protocol):
    """Public retrieval facade protocol matching PROJECT.md Section 4."""

    async def retrieve(
        self, tenant_id: TenantId, query: str, top_k: int = 6
    ) -> list[RetrievedChunk]: ...


class DefaultRetrievalService:
    """Production implementation of RetrievalService protocol."""

    def __init__(self, retriever: Any, reranker: Any = None) -> None:
        self.retriever = retriever
        self.reranker = reranker

    async def retrieve(
        self, tenant_id: TenantId, query: str, top_k: int = 6
    ) -> list[RetrievedChunk]:
        if not query or top_k <= 0:
            return []
        if hasattr(self.retriever, "search"):
            hits = await self.retriever.search(query, tenant_id=tenant_id, k=top_k)
        elif hasattr(self.retriever, "retrieve"):
            hits = await self.retriever.retrieve(query, tenant_id=tenant_id, top_k=top_k)
        else:
            hits = []

        chunks: list[RetrievedChunk] = []
        for h in hits:
            if isinstance(h, RetrievedChunk):
                chunks.append(h)
            else:
                chunks.append(
                    RetrievedChunk(
                        chunk_id=getattr(h, "chunk_id", getattr(h, "id", "")),
                        document_id=str(getattr(h, "document_id", "")),
                        content=getattr(h, "text", getattr(h, "content", "")),
                        score=float(getattr(h, "score", 0.0)),
                        heading_path=list(getattr(h, "heading_path", []) or []),
                        page_number=getattr(h, "page", getattr(h, "page_number", None)),
                        metadata=getattr(h, "metadata", {}) or {},
                    )
                )
        return chunks[:top_k]


class ContextBuilder:
    """Constructs a deduplicated, budget-constrained context pack with citation metadata."""

    def __init__(self, tokenizer: Any, budget_tokens: int) -> None:
        self.tokenizer = tokenizer
        self.budget_tokens = budget_tokens

    def _truncate_to_budget(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within max_tokens using tokenizer."""
        if max_tokens <= 0:
            return ""
        if hasattr(self.tokenizer, "encode") and hasattr(self.tokenizer, "decode"):
            try:
                tokens = self.tokenizer.encode(text)
                if len(tokens) <= max_tokens:
                    return text
                return self.tokenizer.decode(tokens[:max_tokens])
            except Exception:
                pass
        # Fallback to whitespace word splitting
        words = text.split()
        if len(words) <= max_tokens:
            return text
        return " ".join(words[:max_tokens])

    def build(self, hits: list[Hit]) -> ContextPack:
        """Build a ContextPack from retrieved hits respecting deduplication and token budget."""
        if not hits or self.budget_tokens <= 0:
            return ContextPack(passages=[])

        # Sort by score descending
        sorted_hits = sorted(hits, key=lambda h: -h.score)

        seen_chunk_ids: set[str] = set()
        seen_texts: set[str] = set()
        passages: list[Passage] = []
        tokens_used = 0

        for h in sorted_hits:
            if h.chunk_id in seen_chunk_ids:
                continue
            if h.text in seen_texts:
                continue

            seen_chunk_ids.add(h.chunk_id)
            seen_texts.add(h.text)

            remaining = self.budget_tokens - tokens_used
            if remaining <= 0:
                break

            chunk_tokens = self.tokenizer.count(h.text)
            if chunk_tokens <= remaining:
                passage_text = h.text
                tokens_used += chunk_tokens
            else:
                passage_text = self._truncate_to_budget(h.text, remaining)
                tokens_used += self.tokenizer.count(passage_text)

            citation = Citation(
                title=h.title,
                page=h.page,
                heading_path=tuple(h.heading_path) if h.heading_path else (),
            )
            passages.append(
                Passage(
                    chunk_id=h.chunk_id,
                    text=passage_text,
                    citation=citation,
                    score=h.score,
                )
            )

        return ContextPack(passages=passages)


__all__ = [
    "ContextBuilder",
    "DefaultRetrievalService",
    "HybridRetriever",
    "RetrievalService",
    "fuse_hit_rankings",
]
