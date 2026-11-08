"""Structure-aware 5-Pass Hybrid Chunker implementation (ADR 0003).

Goal: Provide robust structure-aware chunking that preserves document hierarchy, prevents table severance,
enriches embedding context with breadcrumbs, and supports optional parent-child and semantic refinement.

Consulted documentation & references:
- ADR 0003: Structure-Aware 5-Pass Hybrid Chunking
- Chonkie (https://github.com/bhavnicksm/chonkie): recursive token windowing and semantic splitting
- LangChain / LlamaIndex markdown table chunking: row splitting with repeated header
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from ragassist.modules.knowledge.adapters.chunkers.passes import (
    context_pass,
    merge_pass,
    structure_pass,
    table_pass,
    token_pass,
)
from ragassist.modules.knowledge.domain import ParsedDocument


@dataclass
class ChunkDraft:
    """A draft chunk produced by chunkers prior to embedding and persistence (ADR 0003)."""

    text: str
    embed_text: str
    heading_path: tuple[str, ...] = ()
    page: int | None = None
    parent: int | None = None
    token_count: int = 0
    _id: UUID = field(default_factory=uuid4)
    _document_id: UUID = field(default_factory=uuid4)
    _tenant_id: UUID | None = None
    _chunk_index: int = 0

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def document_id(self) -> UUID:
        return self._document_id

    @property
    def tenant_id(self) -> UUID | None:
        return self._tenant_id

    @property
    def chunk_index(self) -> int:
        return self._chunk_index

    @property
    def content(self) -> str:
        return self.text

    @property
    def clean_text(self) -> str:
        return self.embed_text

    @property
    def page_number(self) -> int | None:
        return self.page

    @property
    def parent_id(self) -> int | None:
        return self.parent

    def __getitem__(self, key: str) -> Any:
        if key in ("text", "content"):
            return self.text
        if key in ("embed_text", "clean_text"):
            return self.embed_text
        if key == "heading_path":
            return list(self.heading_path)
        if key in ("page", "page_number"):
            return self.page
        if key in ("parent", "parent_id"):
            return self.parent
        if key == "token_count":
            return self.token_count
        if key == "chunk_index":
            return self._chunk_index
        if key == "id":
            return self._id
        if key == "document_id":
            return self._document_id
        if key == "tenant_id":
            return self._tenant_id
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class HybridChunker:
    """Structure-aware 5-pass hybrid chunker (ADR 0003)."""

    name: str = "hybrid"

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 64,
        merge_peers: bool = True,
        tokenizer: Any = None,
        parent_child: bool = False,
        semantic: bool = False,
        semantic_embedder: Any = None,
    ) -> None:
        if semantic and semantic_embedder is None:
            raise ValueError("semantic_embedder is required when semantic=True")

        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.merge_peers = merge_peers
        self.tokenizer = tokenizer
        self.parent_child = parent_child
        self.semantic = semantic
        self.semantic_embedder = semantic_embedder

    @classmethod
    def from_settings(cls, settings: Any, tokenizer: Any) -> HybridChunker:
        max_tokens = getattr(settings, "CHUNK_MAX_TOKENS", 512)
        overlap_tokens = getattr(settings, "CHUNK_OVERLAP_TOKENS", 64)
        merge_peers = getattr(settings, "CHUNK_MERGE_PEERS", True)
        parent_child = getattr(settings, "CHUNK_PARENT_CHILD", False)
        semantic = getattr(settings, "CHUNK_SEMANTIC", False)
        return cls(
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            merge_peers=merge_peers,
            tokenizer=tokenizer,
            parent_child=parent_child,
            semantic=semantic,
        )

    def chunk(self, *args: Any, **kwargs: Any) -> list[ChunkDraft]:
        """Execute chunking over sections or a parsed document."""
        if not args:
            return []

        # Polymorphic argument resolution
        if len(args) >= 3:
            doc_id_raw, tenant_id_raw, raw_sections = args[0], args[1], args[2]
            title = kwargs.get("title", "Document")
        elif len(args) == 1:
            first = args[0]
            doc_id_raw = getattr(first, "document_id", uuid4())
            tenant_id_raw = getattr(first, "tenant_id", None)
            if isinstance(first, ParsedDocument):
                raw_sections = first.blocks
                title = kwargs.get("title", first.title)
            elif isinstance(first, list):
                raw_sections = first
                title = kwargs.get("title", "Document")
            else:
                raw_sections = getattr(first, "blocks", [])
                title = kwargs.get("title", getattr(first, "title", "Document"))
        else:
            doc_id_raw = args[0]
            tenant_id_raw = args[1]
            raw_sections = kwargs.get("sections", [])
            title = kwargs.get("title", "Document")

        document_id = doc_id_raw if isinstance(doc_id_raw, UUID) else UUID(str(doc_id_raw))
        tenant_id = (
            tenant_id_raw
            if isinstance(tenant_id_raw, UUID) or tenant_id_raw is None
            else UUID(str(tenant_id_raw))
        )

        if not raw_sections:
            return []

        # Pass 1: Structure pass
        blocks = structure_pass(raw_sections)
        if not blocks:
            return []

        if self.parent_child:
            parent_max = self.max_tokens * 3
            parent_blocks = token_pass(blocks, max_tokens=parent_max, tokenizer=self.tokenizer)
            if self.merge_peers:
                parent_blocks = merge_pass(parent_blocks, max_tokens=parent_max, tokenizer=self.tokenizer)
            parent_blocks = table_pass(parent_blocks, max_tokens=parent_max, tokenizer=self.tokenizer)

            out_chunks: list[ChunkDraft] = []
            for p_block in parent_blocks:
                parent_idx = len(out_chunks)
                p_draft = context_pass([p_block], title=title)[0]
                p_tokens = self.tokenizer.count(p_draft.text) if self.tokenizer else len(p_draft.text.split())
                p_draft.token_count = p_tokens
                p_draft._chunk_index = parent_idx
                p_draft._document_id = document_id
                p_draft._tenant_id = tenant_id
                out_chunks.append(p_draft)

                child_blocks = token_pass([p_block], max_tokens=self.max_tokens, tokenizer=self.tokenizer)
                child_drafts = context_pass(child_blocks, title=title)
                for cd in child_drafts:
                    cd.parent = parent_idx
                    cd.token_count = self.tokenizer.count(cd.text) if self.tokenizer else len(cd.text.split())
                    cd._chunk_index = len(out_chunks)
                    cd._document_id = document_id
                    cd._tenant_id = tenant_id
                    out_chunks.append(cd)

            return out_chunks

        # Standard 5-pass flow
        # Pass 2: Token pass
        blocks = token_pass(blocks, max_tokens=self.max_tokens, tokenizer=self.tokenizer)

        # Pass 3: Merge pass
        if self.merge_peers:
            blocks = merge_pass(blocks, max_tokens=self.max_tokens, tokenizer=self.tokenizer)

        # Pass 4: Table protection pass
        blocks = table_pass(blocks, max_tokens=self.max_tokens, tokenizer=self.tokenizer)

        # Pass 5: Contextual header pass
        drafts = context_pass(blocks, title=title)

        for i, d in enumerate(drafts):
            d.token_count = self.tokenizer.count(d.text) if self.tokenizer else len(d.text.split())
            d._chunk_index = i
            d._document_id = document_id
            d._tenant_id = tenant_id

        return drafts
