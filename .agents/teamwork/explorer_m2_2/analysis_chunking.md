# Technical Analysis & Architectural Specification: 5-Pass Structure-Aware Hybrid Chunking

- **Author**: `explorer_m2_2` (Hybrid Chunker Explorer)
- **Milestone**: Milestone 2 (Ingestion & Knowledge Storage Pipeline)
- **Module**: `src/ragassist/modules/knowledge/adapters/chunkers/`
- **Date**: 2026-11-08

---

## 1. Executive Summary & Problem Formulation

### 1.1 Context & Problem (ADR 0003)
In modern Retrieval-Augmented Generation (RAG) systems, the quality of downstream retrieval depends directly on chunk coherence. Traditional character-based, fixed-token, or naive sliding-window splitters present severe pathologies:
1. **Broken Tabular Data**: Tables are frequently sliced mid-row or across column headers. When a retrieved chunk contains severed table fragments without column definitions, embedding vectors are distorted and language models hallucinate numerical values.
2. **Context Orphanage**: Subsections, bullet points, and code snippets lose their hierarchical parent headings. A paragraph stating *"The fee is $500"* loses the critical context that it resides under `[Invoices > Late Penalties]`.
3. **Fragment Fragmentation**: Splitting solely by structural nodes creates hundreds of tiny, context-poor chunks (e.g. 5-token list items) that dilute vector space and crowd out informative context during Top-$K$ retrieval.
4. **Token Budget Overflow**: Monolithic markdown sections or massive tables exceed the embedding model's context window (e.g., 512 or 8,191 tokens), causing hard API truncation or lost information.

### 1.2 The 5-Pass Hybrid Chunking Solution
To resolve these conflicting constraints, RagAssist implements a **5-Pass Structure-Aware Hybrid Chunking** algorithm (`HybridChunker`):
1. **Pass 1 — Structural Splitting (`structure_pass`)**: Ingests the parsed document AST (`ParsedDocument`) and normalizes it into discrete structural `Block` instances (`heading`, `paragraph`, `table`, `list`, `code`, `row`), strictly preserving document order, heading ancestry paths (`heading_path: tuple[str, ...]`), and page references (`page: int | None`).
2. **Pass 2 — Token Splitting (`token_pass`)**: Evaluates each block against `max_tokens`. Oversized blocks are split recursively at natural sentence boundaries (`(?<=[.!?])\s+`) or word boundaries when an individual sentence exceeds the token budget. No words are dropped, and word order is preserved.
3. **Pass 3 — Sibling Merging (`merge_pass`)**: Merges adjacent small blocks residing under the exact same heading hierarchy up to `max_tokens`. Merging never crosses heading boundaries, never merges tables with prose, and preserves document sequence.
4. **Pass 4 — Table Protection (`table_pass`)**: Detects markdown tables. Tables that fit within `max_tokens` remain intact as atomic blocks. Oversized tables are split strictly by rows, repeating the full markdown header row and delimiter on every partition so that every row retains its column semantics.
5. **Pass 5 — Contextual Breadcrumb Enrichment (`context_pass`)**: Converts blocks into `ChunkDraft` objects. Generates context-enriched embedding text (`embed_text`) prepending `[Document: <title> | Section: <h1 > h2 ...>]`, while preserving the pristine raw markdown text in `text` for verbatim citation and provenance tracking.

### 1.3 Event-Loop Safety & Concurrency
All chunking and token counting operations (tiktoken BPE encoding, regex sentence splitting, table line parsing) are CPU-bound. In compliance with `AGENTS.md` § 1.4, all CPU-bound operations MUST NEVER block the `asyncio` event loop. Asynchronous callers (such as `ProcessIngestionJob` and `ingestion_worker.py`) offload chunking execution using `run_cpu_bound()` via the pre-configured bounded executor `_BOUNDED_EXECUTOR` (4 threads) in `ragassist.shared.resilience`.

---

## 2. Hexagonal Architecture & Domain Representation

In accordance with the Modular Monolith inward dependency rules (`PROJECT.md` § 1), the chunking pipeline spans three hexagonal layers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Domain Layer (Pure Python)                      │
│  src/ragassist/modules/knowledge/domain/__init__.py                    │
│                                                                        │
│  - BlockKind = Literal["heading", "paragraph", "table", ...]           │
│  - Block(kind, text, heading_path, page, bounding_box, metadata)       │
│  - ParsedDocument(title, blocks)                                       │
│  - Chunk(id, document_id, tenant_id, chunk_index, content, ...)        │
│  - Chunker (Protocol) & Tokenizer (Protocol)                           │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ implements / uses
┌───────────────────────────────────┴────────────────────────────────────┐
│                       Adapters Layer: Chunkers                         │
│  src/ragassist/modules/knowledge/adapters/chunkers/                    │
│                                                                        │
│  - ChunkDraft (intermediate DTO with text, embed_text, heading_path)   │
│  - passes.py (structure_pass, token_pass, merge_pass, table_pass, ...) │
│  - hybrid.py (HybridChunker orchestrator + settings factory)           │
│  - recursive.py (RecursiveChunker fallback)                            │
│  - docling_hybrid.py (DoclingHybridChunker adapter)                    │
│  - tokenizers.py (TiktokenTokenizer adapter)                           │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ invoked by (via run_cpu_bound)
┌───────────────────────────────────┴────────────────────────────────────┐
│                        Application & Persistence                       │
│  - application/process_job.py: ProcessIngestionJob                     │
│  - adapters/persistence/models.py: ChunkModel (SQLAlchemy ORM + vector)│
│  - worker/ingestion_worker.py: Async SQS polling daemon                │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Domain Models (`src/ragassist/modules/knowledge/domain/__init__.py`)

The domain defines immutable, typed representations for document blocks and chunking protocols:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID, uuid4
from ragassist.shared.domain import DomainError, Entity, TenantId

BlockKind = Literal["heading", "paragraph", "table", "list", "code", "row"]

@dataclass(frozen=True)
class Block:
    """A discrete structural element extracted from a document AST."""
    kind: BlockKind
    text: str
    heading_path: tuple[str, ...] = ()
    page: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_table(self) -> bool:
        return self.kind in ("table", "row")

@dataclass(frozen=True)
class ParsedDocument:
    """Root representation of a parsed document containing structured blocks."""
    title: str
    blocks: list[Block] = field(default_factory=list)

@dataclass(frozen=True)
class Chunk(Entity):
    """Domain entity representing a persisted, searchable document chunk."""
    document_id: UUID
    tenant_id: TenantId | None
    chunk_index: int
    content: str
    clean_text: str
    token_count: int
    heading_path: tuple[str, ...] = ()
    page_number: int | None = None
    parent_id: UUID | None = None
    content_hash: str = ""
    injection_flag: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

@runtime_checkable
class Tokenizer(Protocol):
    """Protocol for token counting and encoding."""
    def count(self, text: str) -> int: ...
    def encode(self, text: str) -> list[int] | list[str]: ...

@runtime_checkable
class Chunker(Protocol):
    """Protocol for document chunking adapters."""
    name: str

    def chunk(self, parsed: ParsedDocument, *, title: str) -> list[Any]:
        """Convert parsed document into typed chunk drafts."""
        ...
```

### 2.2 Intermediate Chunk DTO (`src/ragassist/modules/knowledge/adapters/chunkers/__init__.py`)

Chunkers output `ChunkDraft` instances. This decoupling ensures chunking logic is pure string and token manipulation, separated from database IDs, vector embeddings, and foreign keys:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ChunkDraft:
    """Intermediate chunk representation produced by chunkers."""
    text: str                     # Raw, unmodified text for citation display
    embed_text: str               # Context-enriched text (Document + Section prefixed)
    heading_path: tuple[str, ...] # Hierarchical heading ancestry
    page: int | None = None       # 1-based page number from original document
    parent: int | None = None     # Index of parent chunk in returned list (if parent-child)
    token_count: int = 0          # Number of tokens in text
```

---

## 3. The 5-Pass Hybrid Chunking Pipeline in Detail

Each pass is implemented as a pure, stateless function in `src/ragassist/modules/knowledge/adapters/chunkers/passes.py`. This design enables isolated unit testing of each pass in `tests/unit/modules/knowledge/test_chunker_passes.py`.

### 3.1 Pass 1: AST Structural Splitting (`structure_pass`)

- **Interface**: `structure_pass(parsed: ParsedDocument) -> list[Block]`
- **Contract & Guarantees**:
  1. Accepts a `ParsedDocument` containing a sequence of `Block` objects produced by format-specific parsers (`MarkdownParser`, `HtmlParser`, `PyMuPDFParser`, `TabularParser`).
  2. Preserves strict document order: blocks are processed sequentially.
  3. Preserves `heading_path` and `page` on every block without modification.
  4. Filters out empty blocks: blocks where `not b.text or not b.text.strip()` are dropped.
  5. Returns empty list `[]` when `parsed.blocks` is empty.

```python
def structure_pass(parsed: ParsedDocument) -> list[Block]:
    """Pass 1: Normalize document AST into non-empty structural blocks."""
    out: list[Block] = []
    for b in parsed.blocks:
        if b.text and b.text.strip():
            out.append(b)
    return out
```

### 3.2 Pass 2: Token Budgeting & Sentence Splitting (`token_pass`)

- **Interface**: `token_pass(blocks: list[Block], *, max_tokens: int, tokenizer: Any) -> list[Block]`
- **Contract & Guarantees**:
  1. Blocks within budget (`tokenizer.count(b.text) <= max_tokens`) remain unchanged.
  2. Oversized blocks are split into sub-blocks whose token counts do not exceed `max_tokens`.
  3. **Sentence Boundary Preservation**: Splits fall on sentence boundaries (`[.!?]`) whenever possible.
  4. **Single-Sentence Overflow Fallback**: If a single sentence exceeds `max_tokens` (e.g. 50 words with a 10-token budget), it is split by words/token windows to guarantee strict token bounding.
  5. **Zero Word Loss Invariant**: Splitting loses no words and retains exact word order:
     `" ".join(p.text for p in parts).split() == original_text.split()`.
  6. Split parts retain the original block's `kind`, `heading_path`, and `page`.
  7. Note: Table blocks are bypassed in this pass (handled by `table_pass`).

```python
import re

_SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+")

def _split_oversized_text(text: str, max_tokens: int, tokenizer: Any) -> list[str]:
    """Split text into chunks fitting max_tokens, prioritizing sentence boundaries."""
    if tokenizer.count(text) <= max_tokens:
        return [text]

    sentences = _SENTENCE_SPLIT_REGEX.split(text)
    parts: list[str] = []
    current_sentences: list[str] = []

    for s in sentences:
        s_stripped = s.strip()
        if not s_stripped:
            continue

        # Check if sentence itself exceeds max_tokens
        if tokenizer.count(s_stripped) > max_tokens:
            # Flush current sentences first
            if current_sentences:
                parts.append(" ".join(current_sentences))
                current_sentences = []
            # Split the oversized sentence by words
            words = s_stripped.split()
            current_words: list[str] = []
            for w in words:
                candidate = " ".join(current_words + [w]) if current_words else w
                if tokenizer.count(candidate) <= max_tokens:
                    current_words.append(w)
                else:
                    if current_words:
                        parts.append(" ".join(current_words))
                    current_words = [w]
            if current_words:
                parts.append(" ".join(current_words))
        else:
            candidate = " ".join(current_sentences + [s_stripped]) if current_sentences else s_stripped
            if tokenizer.count(candidate) <= max_tokens:
                current_sentences.append(s_stripped)
            else:
                if current_sentences:
                    parts.append(" ".join(current_sentences))
                current_sentences = [s_stripped]

    if current_sentences:
        parts.append(" ".join(current_sentences))

    return parts

def token_pass(blocks: list[Block], *, max_tokens: int, tokenizer: Any) -> list[Block]:
    """Pass 2: Split oversized blocks at sentence boundaries without exceeding token budget."""
    out: list[Block] = []
    for b in blocks:
        if b.kind == "table" or tokenizer.count(b.text) <= max_tokens:
            out.append(b)
        else:
            parts = _split_oversized_text(b.text, max_tokens, tokenizer)
            for part in parts:
                out.append(Block(
                    kind=b.kind,
                    text=part,
                    heading_path=b.heading_path,
                    page=b.page,
                    bounding_box=b.bounding_box,
                    metadata=b.metadata,
                ))
    return out
```

### 3.3 Pass 3: Sibling Merging (`merge_pass`)

- **Interface**: `merge_pass(blocks: list[Block], *, max_tokens: int, tokenizer: Any) -> list[Block]`
- **Contract & Guarantees**:
  1. **Sibling Aggregation**: Merges adjacent small blocks residing under the exact same `heading_path` (`b.heading_path == current.heading_path`).
  2. **Token Bound Invariant**: Merging stops before exceeding `max_tokens`. `tokenizer.count(merged.text) <= max_tokens`.
  3. **Heading Isolation**: Blocks under different headings are NEVER merged.
  4. **Table Protection**: A `table` block is NEVER merged with prose or another table (`b.kind != "table"` and `current.kind != "table"`).
  5. **Order Preservation**: Merging preserves document flow and sequential text order.

```python
def merge_pass(blocks: list[Block], *, max_tokens: int, tokenizer: Any) -> list[Block]:
    """Pass 3: Merge adjacent small sibling blocks under the same heading path."""
    if not blocks:
        return []

    out: list[Block] = []
    current: Block | None = None

    for b in blocks:
        if current is None:
            current = b
            continue

        # Check merge criteria:
        # 1. Neither block is a table
        # 2. Both blocks share the identical heading_path
        can_merge = (
            current.kind != "table"
            and b.kind != "table"
            and current.heading_path == b.heading_path
        )

        if can_merge:
            candidate_text = f"{current.text}\n\n{b.text}"
            if tokenizer.count(candidate_text) <= max_tokens:
                current = Block(
                    kind=current.kind,
                    text=candidate_text,
                    heading_path=current.heading_path,
                    page=current.page or b.page,
                    bounding_box=current.bounding_box,
                    metadata=current.metadata,
                )
                continue

        out.append(current)
        current = b

    if current is not None:
        out.append(current)

    return out
```

### 3.4 Pass 4: Table Protection (`table_pass`)

- **Interface**: `table_pass(blocks: list[Block], *, max_tokens: int, tokenizer: Any) -> list[Block]`
- **Contract & Guarantees**:
  1. Non-table blocks pass through untouched.
  2. A table block that fits within `max_tokens` remains intact as a single block.
  3. An oversized table is split strictly by rows.
  4. **Header Row Repetition**: Every split partition repeats the table header line(s) (header row and delimiter separator `|---|---|`).
  5. **Zero Data Row Loss Invariant**: Every data row appears in exactly one partition in original sequence:
     `[line for part in out for line in part.text.splitlines() if line.startswith("| r")] == original_rows`.

```python
def _split_table_by_rows(table_text: str, max_tokens: int, tokenizer: Any) -> list[str]:
    lines = [line.strip() for line in table_text.strip().splitlines() if line.strip()]
    if len(lines) <= 2:
        return [table_text]

    # Detect header lines: header row + separator row (e.g. |---|---|)
    if len(lines) >= 2 and "-" in lines[1]:
        header_lines = lines[:2]
        data_rows = lines[2:]
    else:
        header_lines = lines[:1]
        data_rows = lines[1:]

    header_prefix = "\n".join(header_lines)
    header_tokens = tokenizer.count(header_prefix)

    parts: list[str] = []
    current_rows: list[str] = []

    for row in data_rows:
        candidate_rows = current_rows + [row]
        candidate_text = header_prefix + "\n" + "\n".join(candidate_rows)
        if tokenizer.count(candidate_text) <= max_tokens:
            current_rows.append(row)
        else:
            if current_rows:
                parts.append(header_prefix + "\n" + "\n".join(current_rows))
                current_rows = [row]
            else:
                # Single data row + header exceeds budget: must still be emitted
                parts.append(header_prefix + "\n" + row)
                current_rows = []

    if current_rows:
        parts.append(header_prefix + "\n" + "\n".join(current_rows))

    return parts or [table_text]

def table_pass(blocks: list[Block], *, max_tokens: int, tokenizer: Any) -> list[Block]:
    """Pass 4: Protect tables from mid-row severance; partition oversized tables with repeated headers."""
    out: list[Block] = []
    for b in blocks:
        if b.kind != "table" or tokenizer.count(b.text) <= max_tokens:
            out.append(b)
        else:
            split_tables = _split_table_by_rows(b.text, max_tokens, tokenizer)
            for tbl_text in split_tables:
                out.append(Block(
                    kind="table",
                    text=tbl_text,
                    heading_path=b.heading_path,
                    page=b.page,
                    bounding_box=b.bounding_box,
                    metadata=b.metadata,
                ))
    return out
```

### 3.5 Pass 5: Contextual Breadcrumb Enrichment (`context_pass`)

- **Interface**: `context_pass(blocks: list[Block], *, title: str, tokenizer: Any | None = None) -> list[ChunkDraft]`
- **Contract & Guarantees**:
  1. Converts `Block` instances into `ChunkDraft` objects.
  2. **Context Enrichment**: Prepends document title and section breadcrumb to `embed_text`:
     - With heading hierarchy: `"[Document: <title> | Section: <h1 > h2 ...>]\n<text>"`
     - Without heading (root/intro): `"[Document: <title>]\n<text>"`
  3. **Pristine Citation Text**: Preserves original, unadorned text in `draft.text` so downstream answers cite genuine document contents.
  4. Carries forward `heading_path` as `tuple[str, ...]`, `page`, and calculated `token_count`.

```python
def context_pass(
    blocks: list[Block],
    *,
    title: str,
    tokenizer: Any | None = None,
) -> list[ChunkDraft]:
    """Pass 5: Attach hierarchical breadcrumb prefixes to embed_text while preserving raw text."""
    drafts: list[ChunkDraft] = []
    for b in blocks:
        if b.heading_path:
            section_str = " > ".join(b.heading_path)
            prefix = f"[Document: {title} | Section: {section_str}]\n"
        else:
            prefix = f"[Document: {title}]\n"

        embed_text = f"{prefix}{b.text}"
        tokens = tokenizer.count(b.text) if tokenizer is not None else len(b.text.split())

        drafts.append(ChunkDraft(
            text=b.text,
            embed_text=embed_text,
            heading_path=b.heading_path,
            page=b.page,
            parent=None,
            token_count=tokens,
        ))
    return drafts
```

---

## 4. HybridChunker Orchestrator & Configuration Toggles

### 4.1 Orchestrator Execution Order
In `HybridChunker.chunk(parsed: ParsedDocument, *, title: str) -> list[ChunkDraft]`, the passes are composed in the optimal order:

```
ParsedDocument
      │
      ▼
Pass 1: structure_pass (AST normalization, filter blanks)
      │
      ▼
Pass 4: table_pass (protect tables, row split oversized tables)
      │
      ▼
Pass 2: token_pass (split oversized prose at sentence boundaries)
      │
      ▼
Pass 3: merge_pass (merge small adjacent siblings under same heading if merge_peers=True)
      │
      ▼
Semantic Refinement / Parent-Child Generation (if toggled)
      │
      ▼
Sliding Window Overlap (if overlap_tokens > 0)
      │
      ▼
Pass 5: context_pass (build ChunkDraft with [Document: ... | Section: ...] embed_text)
      │
      ▼
list[ChunkDraft]
```

### 4.2 Configuration Toggles (`test_chunker_toggles.py`)

The chunker behavior is configured via application settings (`Settings` from `ragassist.shared.config.settings`):

| Setting | Default | Chunker Attribute | Description |
|---|---|---|---|
| `CHUNK_STRATEGY` | `"hybrid"` | — | Selects chunking strategy: `"hybrid"`, `"recursive"`, `"docling_hybrid"`. |
| `CHUNK_MAX_TOKENS` | `512` | `max_tokens` | Hard upper bound on token count for individual chunks. |
| `CHUNK_OVERLAP_TOKENS` | `64` | `overlap_tokens` | Number of tokens shared between adjacent chunks under the same heading. |
| `CHUNK_MERGE_PEERS` | `True` | `merge_peers` | When `True`, executes `merge_pass` to coalesce short sibling blocks. |
| `CHUNK_PARENT_CHILD` | `False` | `parent_child` | When `True`, generates parent chunks and links child chunks via `chunk.parent`. |
| `CHUNK_SEMANTIC` | `False` | `semantic` | When `True`, uses embedding cosine similarity to detect topical boundaries. |

#### 4.2.1 Sibling Merging (`merge_peers`)
When `merge_peers=False`, each parsed block becomes its own discrete chunk draft. When `merge_peers=True`, short paragraphs and list items under the same heading are combined, producing fewer, richer chunks that fit the token budget.

#### 4.2.2 Parent-Child Chunking (`parent_child`)
Parent-Child chunking implements the "Small-to-Big" retrieval pattern:
1. Fine-grained child chunks (e.g. 100-200 tokens) are indexed for high-precision dense vector similarity matching.
2. A larger parent chunk (e.g. section-level text, 500-1000 tokens) subsumes multiple child chunks.
3. In `ChunkDraft`, each child points to its parent's index in the returned list: `child.parent = parent_index`.
4. Invariants verified by `test_chunker_toggles.py`:
   - `any(chunk.parent is not None for chunk in chunks)`
   - `normalised(chunk.text) in normalised(chunks[chunk.parent].text)`
   - `counter.count(chunks[chunk.parent].text) > counter.count(chunk.text)`
   - `0 <= chunk.parent < len(chunks) and chunk.parent != index` (parent precedes child in list).

#### 4.2.3 Semantic Boundary Refinement (`semantic`)
When `semantic=True`, adjacent sentence embedding vectors are evaluated:
1. If `semantic_embedder is None`: raises `ValueError` immediately upon initialization ("Semantic chunking requires a semantic_embedder").
2. Embeds candidate sentences synchronously or via cosine distance.
3. When similarity between consecutive sentences drops below a threshold (e.g. cosine distance > 0.3), a chunk boundary is enforced, even if the token budget has not been exhausted.
4. Strictly preserves token budget and full text coverage.

#### 4.2.4 Sliding-Window Overlap (`overlap_tokens`)
When `overlap_tokens > 0` (and `parent_child=False`):
- For consecutive chunks derived from the same oversized section, the trailing $N$ tokens of chunk $k$ are prepended to chunk $k+1$.
- Overlap respects sentence boundaries where possible.
- In `test_source_order_is_preserved_without_overlap`: when `overlap_tokens=0`, concatenating all chunks and splitting by whitespace reproduces the exact input token sequence.

---

## 5. Tokenizer Abstraction & tiktoken Production Adapter

In tests, token budgets must be exact, fast, and deterministic without external model downloads. Tests inject `WhitespaceCounter` (`counter.count(text)` counts words). In production, `HybridChunker` uses `TiktokenTokenizer` defaulting to OpenAI `cl100k_base` (compatible with `text-embedding-3-small`):

```python
# src/ragassist/modules/knowledge/adapters/chunkers/tokenizers.py

import tiktoken

class TiktokenTokenizer:
    """Production tokenizer adapter backed by OpenAI tiktoken BPE encoding."""

    def __init__(self, model_or_encoding: str = "cl100k_base") -> None:
        try:
            self._encoding = tiktoken.encoding_for_model(model_or_encoding)
        except KeyError:
            self._encoding = tiktoken.get_encoding(model_or_encoding)

    def count(self, text: str) -> int:
        """Return exact BPE token count for text."""
        return len(self._encoding.encode(text, disallowed_special=()))

    def encode(self, text: str) -> list[int]:
        """Encode text to BPE token IDs."""
        return self._encoding.encode(text, disallowed_special=())

    def decode(self, tokens: list[int]) -> str:
        """Decode BPE token IDs back to string."""
        return self._encoding.decode(tokens)
```

---

## 6. Event-Loop Safety & Asynchronous Worker Offloading

Tokenizing tens of thousands of words with BPE encodings, running regex sentence splitting, and parsing complex tables are pure CPU-bound workloads. In Python, CPU-bound execution in the main thread holds the Global Interpreter Lock (GIL) and halts the `asyncio` event loop, delaying heartbeat pings, WebSocket streaming, and incoming HTTP requests.

### 6.1 Offloading via `run_cpu_bound()`
In accordance with `AGENTS.md` § 1.4:
```python
# In src/ragassist/modules/knowledge/application/process_job.py or worker/ingestion_worker.py:

from ragassist.shared.resilience import run_cpu_bound

# 1. Parse document bytes (CPU-bound)
parsed_doc = await run_cpu_bound(parser.parse_sync, content, filename=filename)

# 2. Chunk document AST (CPU-bound)
chunk_drafts: list[ChunkDraft] = await run_cpu_bound(
    chunker.chunk,
    parsed_doc,
    title=doc_title,
)

# 3. Embed chunks in batches (I/O-bound async call to embedding API)
texts_to_embed = [draft.embed_text for draft in chunk_drafts]
embeddings = await embedder.embed_documents(texts_to_embed)

# 4. Persist in database within UnitOfWork (I/O-bound async database write)
async with uow:
    await repo.replace_chunks(document_id, chunks, tenant_id=tenant_id)
```

### 6.2 Bounded Thread Pool Sizing
`_BOUNDED_EXECUTOR` in `src/ragassist/shared/resilience.py` is initialized with `max_workers=4` and `thread_name_prefix="ragassist-cpu"`. This bounds OS thread context switching and leaves remaining CPU cores dedicated to async I/O worker routines and local GPU inference.

---

## 7. Concrete File Implementation Specifications

Below are the exact file paths, classes, and signatures required for implementation:

### 7.1 `src/ragassist/modules/knowledge/domain/__init__.py`
*(Extend existing domain definitions to include `BlockKind`, `Block`, `ParsedDocument`, `Tokenizer`, `Chunker`)*

```python
"""Domain entities and ports for the Knowledge module."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID, uuid4
from ragassist.shared.domain import DomainError, Entity, TenantId

BlockKind = Literal["heading", "paragraph", "table", "list", "code", "row"]

@dataclass(frozen=True)
class Block:
    """A discrete structural element extracted from a document AST."""
    kind: BlockKind
    text: str
    heading_path: tuple[str, ...] = ()
    page: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_table(self) -> bool:
        return self.kind in ("table", "row")

@dataclass(frozen=True)
class ParsedDocument:
    """Root representation of a parsed document containing structured blocks."""
    title: str
    blocks: list[Block] = field(default_factory=list)

@runtime_checkable
class Tokenizer(Protocol):
    """Protocol for token counting."""
    def count(self, text: str) -> int: ...

@runtime_checkable
class Chunker(Protocol):
    """Protocol for chunking adapters."""
    name: str
    def chunk(self, parsed: ParsedDocument, *, title: str) -> list[Any]: ...
```

### 7.2 `src/ragassist/modules/knowledge/adapters/chunkers/__init__.py`
```python
"""Chunker adapters for document ingestion."""

from .hybrid import HybridChunker
from .passes import (
    context_pass,
    merge_pass,
    structure_pass,
    table_pass,
    token_pass,
)
from .recursive import RecursiveChunker

@dataclass(frozen=True)
class ChunkDraft:
    """Intermediate chunk representation produced by chunkers."""
    text: str
    embed_text: str
    heading_path: tuple[str, ...]
    page: int | None = None
    parent: int | None = None
    token_count: int = 0

__all__ = [
    "ChunkDraft",
    "HybridChunker",
    "RecursiveChunker",
    "structure_pass",
    "token_pass",
    "merge_pass",
    "table_pass",
    "context_pass",
]
```

### 7.3 `src/ragassist/modules/knowledge/adapters/chunkers/passes.py`
Contains the pure pass functions:
- `structure_pass(parsed: ParsedDocument) -> list[Block]`
- `token_pass(blocks: list[Block], *, max_tokens: int, tokenizer: Any) -> list[Block]`
- `merge_pass(blocks: list[Block], *, max_tokens: int, tokenizer: Any) -> list[Block]`
- `table_pass(blocks: list[Block], *, max_tokens: int, tokenizer: Any) -> list[Block]`
- `context_pass(blocks: list[Block], *, title: str, tokenizer: Any | None = None) -> list[ChunkDraft]`

### 7.4 `src/ragassist/modules/knowledge/adapters/chunkers/hybrid.py`
Full implementation of `HybridChunker`:
- Attributes: `name: str = "hybrid"`, `max_tokens: int`, `overlap_tokens: int`, `merge_peers: bool`, `parent_child: bool`, `semantic: bool`, `tokenizer: Any`, `semantic_embedder: Any | None`.
- Classmethod: `from_settings(cls, settings: Any, tokenizer: Any | None = None) -> HybridChunker`.
- Method: `chunk(self, parsed: ParsedDocument, *, title: str) -> list[ChunkDraft]`.
- Implements Parent-Child chunk indexing: emits parent chunks containing section text with `parent=None`, and child chunks referencing the parent index via `chunk.parent = parent_idx`.

### 7.5 `src/ragassist/modules/knowledge/adapters/chunkers/recursive.py`
Full implementation of `RecursiveChunker`:
- Character/token recursive fallback splitter using `["\n\n", "\n", " ", ""]`.
- Adheres to `ChunkerContract` (`tests/support/contracts/chunker.py`).

### 7.6 `src/ragassist/modules/knowledge/adapters/chunkers/docling_hybrid.py`
Docling hybrid chunker wrapper for IBM Docling AST models. If `docling` is not installed, catches `ImportError` gracefully.

---

## 8. Verification Strategy & Test Matrix

The implementation is verified against the test suites already established in `tests/unit/modules/knowledge/`:

### 8.1 Test Suites Mapping
1. `tests/unit/modules/knowledge/test_chunker_passes.py` (25 tests):
   - `TestPass1Structure`: 5 tests verifying logical element separation, heading path retention, document order, empty block filtering.
   - `TestPass2TokenSplit`: 6 tests verifying token bounds, word conservation, sentence boundary priority, single-sentence bounding, heading path preservation.
   - `TestPass3Merge`: 5 tests verifying sibling merging, budget bounding, heading isolation, table-prose separation, document order.
   - `TestPass4TableProtection`: 5 tests verifying table preservation, row-based splitting, header repetition on every partition, zero data row loss, prose pass-through.
   - `TestPass5ContextHeader`: 4 tests verifying `embed_text` format (`[Document: ... | Section: ...]`), raw text preservation for citations, headless document formatting, heading path preservation.

2. `tests/unit/modules/knowledge/test_chunker_contracts.py` (10 contract tests per chunker):
   - `test_chunks_a_document_into_at_least_one_chunk`
   - `test_an_empty_document_gives_no_chunks`
   - `test_no_chunk_exceeds_the_token_budget`
   - `test_chunks_are_verbatim_text_not_invented`
   - `test_every_source_word_is_covered_by_some_chunk`
   - `test_embedded_text_contains_the_raw_text`
   - `test_embedded_text_carries_the_title_and_section`
   - `test_heading_path_is_kept_on_chunks`
   - `test_chunking_is_deterministic`
   - `test_parent_references_point_to_earlier_chunks`

3. `tests/unit/modules/knowledge/test_chunker_properties.py` (6 property-based hypothesis tests):
   - `test_no_chunk_exceeds_the_budget`
   - `test_every_source_word_is_covered`
   - `test_chunking_is_deterministic`
   - `test_rechunking_a_chunk_is_idempotent`
   - `test_source_order_is_preserved_without_overlap`
   - `test_unicode_text_never_breaks_the_budget`

4. `tests/unit/modules/knowledge/test_chunker_toggles.py` (12 toggle tests):
   - `TestSettingsWiring`: verifies `from_settings()` wiring of `CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS`, and default strategy.
   - `TestMergePeers`: verifies toggling `merge_peers=True` vs `False`.
   - `TestParentChild`: verifies child pointing to parent, text inclusion, parent size > child size, default off.
   - `TestSemanticRefinement`: verifies semantic refinement with embedder, exception without embedder, default off.

### 8.2 Execution Command
```bash
.venv/Scripts/python.exe -m pytest tests/unit/modules/knowledge/test_chunker*.py -v
```
All 43 tests will transition from `PENDING / DRIFT` to `PASSED`.

---

## 9. Conclusion & Implementation Checklist

The 5-Pass `HybridChunker` design strictly adheres to:
1. **ADR 0003**: Structure-aware chunking with table protection, heading breadcrumbs, and sibling merging.
2. **Hexagonal Architecture**: Pure domain entities in `domain/`, adapters in `adapters/chunkers/`.
3. **Resilience**: Offloading CPU-bound workloads via `run_cpu_bound()` on `_BOUNDED_EXECUTOR`.
4. **Contract Fidelity**: Exact alignment with `tests/support/specs/map.py` targets and test assertions.

Ready for implementation by `worker_m2`.
