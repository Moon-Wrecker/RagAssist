"""Pure functions implementing the 5-pass structure-aware hybrid chunking algorithm (ADR 0003).

Goal: Transform parsed document blocks into bounded, context-enriched chunks without severing tables
or losing semantic grounding.

Consulted documentation & references:
- ADR 0003: Structure-Aware 5-Pass Hybrid Chunking
- Chonkie (https://github.com/bhavnicksm/chonkie): structure-aware window splitting
- Markdown table splitters: preserving header row across table splits

Pass 1: Structure Pass - Document hierarchy AST into discrete semantic blocks.
Pass 2: Token Pass - Split oversized blocks at sentence/word boundaries within token budget.
Pass 3: Merge Pass - Merge adjacent undersized sibling prose blocks under the same heading path.
Pass 4: Table Protection Pass - Preserve whole markdown tables; split oversized tables by rows repeating header.
Pass 5: Contextual Header Pass - Prepend document title and section breadcrumbs for embedding text.
"""

from __future__ import annotations

import re
from typing import Any

from ragassist.modules.knowledge.domain import Block, ParsedDocument


def _to_block(item: Any) -> Block:
    if isinstance(item, Block):
        return item
    if isinstance(item, dict):
        kind = item.get("kind") or item.get("type", "paragraph")
        text = item.get("text", "")
        heading_path = tuple(item.get("heading_path") or ())
        page = item.get("page") or item.get("page_number")
        return Block(kind=kind, text=text, heading_path=heading_path, page=page)
    kind = getattr(item, "kind", getattr(item, "type", "paragraph"))
    text = getattr(item, "text", "")
    heading_path = tuple(getattr(item, "heading_path", ()))
    page = getattr(item, "page", getattr(item, "page_number", None))
    return Block(kind=kind, text=text, heading_path=heading_path, page=page)


def structure_pass(parsed: Any) -> list[Block]:
    """Pass 1: Filter empty blocks, retaining one block per logical element with heading paths."""
    raw_list: list[Any]
    if isinstance(parsed, ParsedDocument):
        raw_list = parsed.blocks
    elif isinstance(parsed, list):
        raw_list = parsed
    else:
        raw_list = getattr(parsed, "blocks", [])

    out: list[Block] = []
    for item in raw_list:
        b = _to_block(item)
        if b.text and b.text.strip():
            out.append(b)
    return out


def token_pass(
    blocks: list[Any],
    *,
    max_tokens: int,
    tokenizer: Any,
) -> list[Block]:
    """Pass 2: Split oversized non-table blocks at sentence boundaries up to max_tokens."""
    out: list[Block] = []

    for item in blocks:
        b = _to_block(item)
        if b.kind == "table" or tokenizer.count(b.text) <= max_tokens:
            out.append(b)
            continue

        # Split block text into sentences while preserving trailing punctuation
        sents = [s.strip() for s in re.findall(r".*?[.!?]+(?=\s+|$)|.+", b.text) if s.strip()]

        current_sents: list[str] = []
        for sent in sents:
            if tokenizer.count(sent) > max_tokens:
                # Flush accumulated sentences first
                if current_sents:
                    out.append(
                        Block(
                            kind=b.kind,
                            text=" ".join(current_sents),
                            heading_path=b.heading_path,
                            page=b.page,
                        )
                    )
                    current_sents = []

                # Split the single oversized sentence by words
                words = sent.split()
                curr_words: list[str] = []
                for w in words:
                    candidate = " ".join(curr_words + [w])
                    if tokenizer.count(candidate) <= max_tokens:
                        curr_words.append(w)
                    else:
                        if curr_words:
                            out.append(
                                Block(
                                    kind=b.kind,
                                    text=" ".join(curr_words),
                                    heading_path=b.heading_path,
                                    page=b.page,
                                )
                            )
                        curr_words = [w]
                if curr_words:
                    out.append(
                        Block(
                            kind=b.kind,
                            text=" ".join(curr_words),
                            heading_path=b.heading_path,
                            page=b.page,
                        )
                    )
            else:
                candidate = " ".join(current_sents + [sent])
                if tokenizer.count(candidate) <= max_tokens:
                    current_sents.append(sent)
                else:
                    if current_sents:
                        out.append(
                            Block(
                                kind=b.kind,
                                text=" ".join(current_sents),
                                heading_path=b.heading_path,
                                page=b.page,
                            )
                        )
                    current_sents = [sent]

        if current_sents:
            out.append(
                Block(
                    kind=b.kind,
                    text=" ".join(current_sents),
                    heading_path=b.heading_path,
                    page=b.page,
                )
            )

    return out


def merge_pass(
    blocks: list[Any],
    *,
    max_tokens: int,
    tokenizer: Any,
) -> list[Block]:
    """Pass 3: Merge adjacent sibling prose blocks under the same heading_path while within max_tokens."""
    if not blocks:
        return []

    out: list[Block] = []
    current: Block | None = None

    for item in blocks:
        b = _to_block(item)
        if current is None:
            current = b
            continue

        can_merge = (
            current.kind != "table"
            and b.kind != "table"
            and current.heading_path == b.heading_path
        )

        if can_merge:
            merged_text = f"{current.text}\n\n{b.text}"
            if tokenizer.count(merged_text) <= max_tokens:
                current = Block(
                    kind=current.kind if current.kind == b.kind else "paragraph",
                    text=merged_text,
                    heading_path=current.heading_path,
                    page=current.page or b.page,
                )
                continue

        out.append(current)
        current = b

    if current is not None:
        out.append(current)

    return out


def table_pass(
    blocks: list[Any],
    *,
    max_tokens: int,
    tokenizer: Any,
) -> list[Block]:
    """Pass 4: Table protection - whole table preserved if within budget, else split by rows repeating header."""
    out: list[Block] = []

    for item in blocks:
        b = _to_block(item)
        if b.kind != "table" or tokenizer.count(b.text) <= max_tokens:
            out.append(b)
            continue

        lines = [line.strip() for line in b.text.strip().splitlines() if line.strip()]
        if not lines:
            continue

        if len(lines) >= 2 and lines[1].startswith("|") and ("-" in lines[1] or ":" in lines[1]):
            header_lines = lines[:2]
            data_rows = lines[2:]
        else:
            header_lines = lines[:1]
            data_rows = lines[1:]

        current_rows: list[str] = []
        for row in data_rows:
            candidate_text = "\n".join(header_lines + current_rows + [row])
            if tokenizer.count(candidate_text) <= max_tokens:
                current_rows.append(row)
            else:
                if current_rows:
                    part_text = "\n".join(header_lines + current_rows)
                    out.append(
                        Block(
                            kind="table",
                            text=part_text,
                            heading_path=b.heading_path,
                            page=b.page,
                        )
                    )
                    current_rows = [row]
                else:
                    part_text = "\n".join(header_lines + [row])
                    out.append(
                        Block(
                            kind="table",
                            text=part_text,
                            heading_path=b.heading_path,
                            page=b.page,
                        )
                    )
                    current_rows = []

        if current_rows:
            part_text = "\n".join(header_lines + current_rows)
            out.append(
                Block(
                    kind="table",
                    text=part_text,
                    heading_path=b.heading_path,
                    page=b.page,
                )
            )

    return out


def context_pass(
    blocks: list[Any],
    *,
    title: str,
) -> list[Any]:
    """Pass 5: Contextual header - prepend document and section breadcrumbs to embed_text while keeping text raw."""
    from ragassist.modules.knowledge.adapters.chunkers import ChunkDraft

    drafts: list[ChunkDraft] = []
    for item in blocks:
        b = _to_block(item)
        heading_path = tuple(b.heading_path)
        if heading_path:
            section_str = " > ".join(heading_path)
            prefix = f"[Document: {title} | Section: {section_str}]"
        else:
            prefix = f"[Document: {title}]"

        embed_text = f"{prefix}\n{b.text}"
        token_count = len(b.text.split())

        drafts.append(
            ChunkDraft(
                text=b.text,
                embed_text=embed_text,
                heading_path=heading_path,
                page=b.page,
                parent=None,
                token_count=token_count,
            )
        )

    return drafts
