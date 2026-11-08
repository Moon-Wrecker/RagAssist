"""Domain entities and pure ranking algorithms for retrieval."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    """Retrieved document chunk matching PROJECT.md Section 4 contract."""

    chunk_id: UUID
    document_id: UUID
    content: str
    score: float
    heading_path: str | None = None
    page_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class Hit:
    """A retrieved document chunk matching a query."""

    chunk_id: str
    document_id: str
    tenant_id: str | None
    score: float
    text: str
    heading_path: tuple[str, ...] = ()
    page: int | None = None
    title: str = ""


@dataclass(frozen=True)
class Citation:
    """Provenance metadata for an answer citation."""

    title: str = ""
    page: int | None = None
    heading_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class Passage:
    """A clean text passage formatted for prompt context injection."""

    chunk_id: str
    text: str
    citation: Citation
    score: float = 0.0


@dataclass(frozen=True)
class ContextPack:
    """Packed context passages fitting within LLM context budget."""

    passages: list[Passage]

    def to_spotlight_text(self) -> str:
        """Render passages in spotlight XML tag format: <document id="...">...</document>."""
        parts: list[str] = []
        for passage in self.passages:
            attrs = [f'id="{passage.chunk_id}"']
            if passage.citation.title:
                attrs.append(f'title="{passage.citation.title}"')
            if passage.citation.page is not None:
                attrs.append(f'page="{passage.citation.page}"')
            if passage.citation.heading_path:
                section_str = " > ".join(passage.citation.heading_path)
                attrs.append(f'section="{section_str}"')

            tag_open = f"<document {' '.join(attrs)}>"
            parts.append(f"{tag_open}\n{passage.text.strip()}\n</document>")
        return "\n\n".join(parts)


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion (RRF) across multiple ranked lists.

    Score = sum over rankings of 1 / (k + rank), where rank is 1-based.
    An ID repeated inside one ranking counts only at its best (first) rank.
    Results are sorted by score descending, with ties broken by first appearance.
    """
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    counter = 0

    for ranking in rankings:
        seen_here: set[str] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen_here:
                continue
            seen_here.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            if item not in first_seen:
                first_seen[item] = counter
                counter += 1

    return sorted(scores.items(), key=lambda pair: (-pair[1], first_seen[pair[0]]))


__all__ = [
    "Citation",
    "ContextPack",
    "Hit",
    "Passage",
    "RetrievedChunk",
    "reciprocal_rank_fusion",
]
