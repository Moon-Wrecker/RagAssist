"""Recursive text chunker adapter."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from ragassist.modules.knowledge.adapters.chunkers.hybrid_chunker import ChunkDraft
from ragassist.modules.knowledge.adapters.chunkers.passes import (
    context_pass,
    structure_pass,
    token_pass,
)
from ragassist.modules.knowledge.domain import ParsedDocument


class RecursiveChunker:
    """Standard recursive character/token chunker."""

    name: str = "recursive"

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 64,
        tokenizer: Any = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.tokenizer = tokenizer

    def chunk(self, *args: Any, **kwargs: Any) -> list[ChunkDraft]:
        if not args:
            return []

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

        blocks = structure_pass(raw_sections)
        if not blocks:
            return []

        blocks = token_pass(blocks, max_tokens=self.max_tokens, tokenizer=self.tokenizer)
        drafts = context_pass(blocks, title=title)

        for i, d in enumerate(drafts):
            d.token_count = self.tokenizer.count(d.text) if self.tokenizer else len(d.text.split())
            d._chunk_index = i
            d._document_id = document_id
            d._tenant_id = tenant_id

        return drafts
