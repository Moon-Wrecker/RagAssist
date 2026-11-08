# Technical Analysis & Architectural Specification: Document AST Parsers

- **Author**: `explorer_m2_1` (Document Parsers Explorer)
- **Milestone**: Milestone 2 (Ingestion & Knowledge Storage Pipeline)
- **Module**: `src/ragassist/modules/knowledge/`
- **Date**: 2026-11-08

---

## 1. Executive Summary

Document parsing is the initial phase of the RagAssist ingestion pipeline. Its responsibility is to ingest raw binary streams of varying MIME types (`application/pdf`, `text/html`, `text/markdown`, `text/csv`, `text/plain`), perform structural analysis, sanitize unsafe payloads, and construct an Abstract Syntax Tree (AST) represented canonically as `ParsedDocument` containing a sequence of typed `Block` instances.

Key architectural requirements:
1. **Hexagonal Domain Purity**: Document AST representations (`ParsedDocument`, `Block`, `BlockKind`) and domain exceptions (`ParseError`, `UnsupportedMimeType`, `FileTooLarge`) reside strictly in `src/ragassist/modules/knowledge/domain/`.
2. **Event-Loop Safety**: All parsing workloads are CPU-intensive (especially C-based PyMuPDF extraction and regex/HTML parsing). They must NEVER execute directly on the `asyncio` event loop thread. Every parser offloads parsing to `run_cpu_bound()` via the pre-configured bounded executor `_BOUNDED_EXECUTOR` in `ragassist.shared.resilience`.
3. **Structural Fidelity**:
   - Headings construct an active hierarchical breadcrumb stack (`heading_path: tuple[str, ...]`), vital for downstream chunk contextualization.
   - Tables are extracted as complete, contiguous Markdown tables (`kind="table"`).
   - Tabular CSV/TSV data converts each data record into a `row` block that repeats column headers, ensuring self-contained semantic relevance during vector search.
   - Page numbers (`page: int | None`) are strictly preserved for PDF documents (1-based indexing) to enable accurate citations.
4. **Defensive Edge Case Handling**:
   - Script/style tags and malicious HTML code are stripped to prevent prompt injection or XSS leakage.
   - Non-UTF-8 encodings (Latin-1, CP1252, Shift-JIS) are safely normalized without raising uncaught `UnicodeDecodeError`.
   - Corrupted or password-protected PDFs raise typed `ParseError`.
   - Empty files produce empty block lists without failing.
   - Massive uploads exceeding the size limit (50MB) raise `FileTooLarge`.

---

## 2. Document AST Data Structures & Domain Models

### 2.1 Canonical Block & ParsedDocument Contract

The downstream 5-pass `HybridChunker` (`tests/unit/modules/knowledge/test_chunker_passes.py`) and the test suites (`test_parser_contracts.py`, `test_parser_behaviour.py`) require the following domain contracts in `src/ragassist/modules/knowledge/domain/__init__.py`:

```python
from dataclasses import dataclass, field
from typing import Any, Literal
from ragassist.shared.domain import DomainError

BlockKind = Literal["heading", "paragraph", "table", "list", "code", "row"]

@dataclass(frozen=True)
class Block:
    """A discrete structural element extracted from a document."""
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
    """Root representation of a parsed document."""
    title: str
    blocks: list[Block] = field(default_factory=list)
```

### 2.2 Rich AST Hierarchy (`domain/ast.py`)

To support advanced document understanding, layout-aware reasoning, and future visual sidecar viewers, the internal object model defines an explicit AST node hierarchy that maps cleanly into canonical `Block` objects:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from . import Block, BlockKind

@dataclass
class BaseASTNode(ABC):
    """Abstract base node in the Document AST."""
    heading_path: tuple[str, ...] = ()
    page_number: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None  # (x0, y0, x1, y1)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    @abstractmethod
    def kind(self) -> BlockKind:
        """The canonical block kind."""
        ...

    @abstractmethod
    def to_text(self) -> str:
        """Render node content to formatted text."""
        ...

    def to_block(self) -> Block:
        """Convert AST node to canonical immutable Block."""
        return Block(
            kind=self.kind,
            text=self.to_text(),
            heading_path=self.heading_path,
            page=self.page_number,
            bounding_box=self.bounding_box,
            metadata=self.metadata,
        )

@dataclass
class HeadingNode(BaseASTNode):
    level: int  # 1 to 6
    text: str

    @property
    def kind(self) -> BlockKind:
        return "heading"

    def to_text(self) -> str:
        return self.text

@dataclass
class ParagraphNode(BaseASTNode):
    text: str

    @property
    def kind(self) -> BlockKind:
        return "paragraph"

    def to_text(self) -> str:
        return self.text

@dataclass
class TableNode(BaseASTNode):
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    raw_markdown: str = ""

    @property
    def kind(self) -> BlockKind:
        return "table"

    def to_text(self) -> str:
        if self.raw_markdown:
            return self.raw_markdown.strip()
        # Build GFM markdown table
        header_line = "| " + " | ".join(self.headers) + " |"
        sep_line = "| " + " | ".join("---" for _ in self.headers) + " |"
        data_lines = ["| " + " | ".join(row) + " |" for row in self.rows]
        return "\n".join([header_line, sep_line] + data_lines)

@dataclass
class CodeNode(BaseASTNode):
    code: str
    language: str | None = None

    @property
    def kind(self) -> BlockKind:
        return "code"

    def to_text(self) -> str:
        return self.code

@dataclass
class ListNode(BaseASTNode):
    items: list[str] = field(default_factory=list)
    ordered: bool = False

    @property
    def kind(self) -> BlockKind:
        return "list"

    def to_text(self) -> str:
        if self.ordered:
            return "\n".join(f"{i+1}. {item}" for i, item in enumerate(self.items))
        return "\n".join(f"- {item}" for item in self.items)

@dataclass
class RowNode(BaseASTNode):
    headers: list[str]
    values: list[str]

    @property
    def kind(self) -> BlockKind:
        return "row"

    def to_text(self) -> str:
        # Repeats column headers for standalone semantic relevance
        return ", ".join(f"{h}: {v}" for h, v in zip(self.headers, self.values))

@dataclass
class DocumentNode:
    title: str
    nodes: list[BaseASTNode] = field(default_factory=list)

    def to_parsed_document(self) -> ParsedDocument:
        return ParsedDocument(
            title=self.title,
            blocks=[node.to_block() for node in self.nodes],
        )
```

### 2.3 Domain Exceptions

All domain exceptions inherit from `ragassist.shared.domain.DomainError`:

```python
class ParseError(DomainError):
    """Raised when document parsing fails due to corruption or malformed content."""

class UnsupportedMimeType(DomainError):
    """Raised when a document parser cannot handle the requested MIME type (HTTP 415)."""

class FileTooLarge(DomainError):
    """Raised when uploaded file exceeds max allowed size (HTTP 413)."""

class PasswordProtectedError(ParseError):
    """Raised when an encrypted PDF cannot be unlocked with a blank password."""
```

---

## 3. Parser Protocol & Base Adapter Architecture

### 3.1 Port Protocol

Located in `src/ragassist/modules/knowledge/domain/__init__.py`:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Parser(Protocol):
    """Protocol for document parsing adapters."""
    name: str
    mimes: tuple[str, ...]

    def supports(self, mime: str) -> bool:
        """Return True if this parser can handle the given MIME type."""
        ...

    async def parse(self, content: bytes, *, mime: str, filename: str) -> ParsedDocument:
        """Parse raw document bytes into a canonical ParsedDocument."""
        ...
```

### 3.2 Base Parser Implementation (`adapters/parsers/base.py`)

The `BaseParser` handles:
1. MIME type validation (`supports(mime)`).
2. Offloading CPU-bound synchronous parsing to `run_cpu_bound()`.
3. Safe text decoding across varied character sets without crashing on `UnicodeDecodeError`.

```python
from abc import ABC, abstractmethod
from typing import Any
import structlog
from ragassist.shared.resilience import run_cpu_bound
from ...domain import ParsedDocument, UnsupportedMimeType

logger = structlog.get_logger(__name__)

class BaseParser(ABC):
    """Base adapter implementing async run_cpu_bound offload and safe decoding."""
    name: str = "base"
    mimes: tuple[str, ...] = ()

    def supports(self, mime: str) -> bool:
        return mime in self.mimes

    async def parse(self, content: bytes, *, mime: str, filename: str) -> ParsedDocument:
        if not self.supports(mime):
            raise UnsupportedMimeType(f"Parser '{self.name}' does not support MIME type '{mime}'")
        return await run_cpu_bound(self._parse_sync, content, mime, filename)

    @abstractmethod
    def _parse_sync(self, content: bytes, mime: str, filename: str) -> ParsedDocument:
        """Synchronous parsing routine executed within the bounded thread pool."""
        ...

    @staticmethod
    def safe_decode(content: bytes) -> str:
        """Multi-stage character set decoding:
        1. Fast UTF-8 decode
        2. Charset normalizer detection (if available)
        3. Latin-1 fallback (maps all 256 bytes without error)
        4. UTF-8 replace fallback
        """
        if not content:
            return ""
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            pass

        try:
            import charset_normalizer
            matches = charset_normalizer.from_bytes(content)
            best = matches.best()
            if best and best.encoding:
                return str(best)
        except Exception:
            pass

        try:
            return content.decode("latin-1")
        except Exception:
            return content.decode("utf-8", errors="replace")
```

---

## 4. Format-Specific Parser Specifications

### 4.1 Markdown Parser (`MarkdownParser`)
- **Target File**: `src/ragassist/modules/knowledge/adapters/parsers/markdown.py`
- **Supported MIMEs**: `("text/markdown", "text/x-markdown")`
- **Name**: `"markdown"`
- **Heading Path Algorithm**:
  A heading stack `stack: list[tuple[int, str]]` tracks the active heading lineage.
  - On `# H1`: `stack = [(1, "H1")]` -> `heading_path = ("H1",)`
  - On `## H2`: `stack = [(1, "H1"), (2, "H2")]` -> `heading_path = ("H1", "H2")`
  - On `### H3`: `stack = [(1, "H1"), (2, "H2"), (3, "H3")]` -> `heading_path = ("H1", "H2", "H3")`
  - On `## H2_New`: pop level 3 and level 2 -> `stack = [(1, "H1"), (2, "H2_New")]`
  - Every block emitted inherits `tuple(h for _, h in stack)`.
- **Structural Blocks**:
  1. `heading`: The heading itself is emitted as a `kind="heading"` block so heading-only documents or solitary headings are never lost (`TestMarkdownStructure.test_a_heading_only_document_is_not_lost`).
  2. `table`: Contiguous Markdown table rows (starting with `|`) are combined into a single `kind="table"` block (`TestMarkdownStructure.test_a_table_is_one_table_block`).
  3. `code`: Fenced code blocks (` ``` ` to ` ``` `) are extracted as a single `kind="code"` block preserving indentation and body (`TestMarkdownStructure.test_a_code_fence_is_one_code_block_with_its_body`).
  4. `paragraph`: Regular text blocks separated by double newlines (`\n\n`).
- **Page Numbers**: Always `page = None` for Markdown.

### 4.2 HTML Parser (`HtmlParser`)
- **Target File**: `src/ragassist/modules/knowledge/adapters/parsers/html.py`
- **Supported MIMEs**: `("text/html", "application/xhtml+xml")`
- **Name**: `"html"`
- **Sanitization & Script Stripping**:
  - Unsafe tags (`<script>`, `<style>`, `<noscript>`, `<iframe>`, `<object>`) and their enclosed contents MUST be discarded completely.
  - Test requirement (`TestHtmlStructure.test_script_content_is_dropped`): Any `<script>alert('x')</script>` must result in zero `"alert("` strings in any parsed block.
  - Implementation approach:
    Use regex/HTML parser or BeautifulSoup to purge unwanted tags:
    ```python
    import re
    # Remove script and style tags along with inner content
    clean_html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    ```
- **Markdown Conversion**:
  - `markdownify.markdownify(clean_html, heading_style="ATX", strip=['script', 'style'])` converts HTML elements into clean Markdown syntax (`#` headings, `|` tables, `*` lists).
  - Feed the converted markdown into the hierarchical markdown AST block emitter.
- **Table Preservation**:
  - Table cells and rows are preserved in standard GFM Markdown format (`assert "pro" in table.text and "490" in table.text`).
- **Title Extraction**:
  - Extracted from `<title>...</title>` or the first `<h1>` element.

### 4.3 PDF Parser (`PyMuPDFParser` / `PDFParser`)
- **Target File**: `src/ragassist/modules/knowledge/adapters/parsers/pymupdf.py`
- **Supported MIMEs**: `("application/pdf",)`
- **Name**: `"pymupdf"` (aliases `PDFParser`)
- **Engine**: PyMuPDF (`fitz`) and `pymupdf4llm`
- **Table Structure Extraction**:
  - `pymupdf4llm.to_markdown(doc, pages=[page_idx])` or `pymupdf4llm.to_markdown(doc, page_chunks=True)` analyzes visual vector rectangles and cell alignments, converting PDF tables into clean Markdown tables.
- **Page Number Preservation**:
  - Every page $P \in [0, N-1]$ produces blocks tagged with 1-based page number: `page = P + 1`.
  - Ensures `find(parsed.blocks, "page one").page == 1` and `find(parsed.blocks, "page two").page == 2` as required by `TestPdfPages`.
  - Multi-page document preservation: every page is processed, and all blocks retain their correct page numbers.
- **Heading Lineage in PDF**:
  - `pymupdf4llm` converts larger, bold font spans into Markdown ATX headings (`# Heading`).
  - As pages are iterated sequentially, the heading stack persists across page boundaries, enabling blocks on subsequent pages to inherit the section heading context from prior pages.
- **Corrupt & Password Protection Handling**:
  - Inspect magic bytes: content must begin with `%PDF-`.
  - `fitz.open(stream=content, filetype="pdf")` is wrapped in try-catch. Any `fitz.FileDataError`, `ValueError`, or syntax failure raises `ParseError`.
  - Check `doc.is_encrypted` or `doc.needs_pass`: attempt `doc.authenticate("")`. If the document remains locked, raise `ParseError("PDF document is password protected")`.

### 4.4 Tabular Parser (`TabularParser`)
- **Target File**: `src/ragassist/modules/knowledge/adapters/parsers/tabular.py`
- **Supported MIMEs**: `("text/csv", "text/tab-separated-values")`
- **Name**: `"tabular"`
- **Header-Repeated Row Representation**:
  - To prevent individual chunk searches from losing context, each CSV row is transformed into a `kind="row"` block where column headers are repeated (`TestCsvRows.test_each_row_is_a_row_block_that_repeats_the_header`).
  - Example row representation:
    `plan: pro, price: 490, currency: EUR`
    Satisfies:
    `assert all("plan" in row.text and "price" in row.text for row in rows)`
    `assert any("490" in block.text for block in parsed.blocks)`
- **CSV Dialect & Quoting**:
  - Uses `csv.reader` to respect RFC 4180 quotes. Quoted commas (e.g. `pro,"a, b"`) stay inside one cell (`TestCsvRows.test_a_quoted_comma_stays_inside_one_cell`).
  - Handles CRLF (`\r\n`) and LF (`\n`) seamlessly.
- **Header-Only CSV**:
  - If the CSV contains only a header row with no data rows, `rows = []` is returned (`TestCsvRows.test_a_header_only_file_has_no_rows`).

### 4.5 Plain Text Parser (`PlainTextParser`)
- **Target File**: `src/ragassist/modules/knowledge/adapters/parsers/plain_text.py`
- **Supported MIMEs**: `("text/plain",)`
- **Name**: `"plain_text"`
- **Processing**:
  - Splits text into paragraphs by double newlines `\n\n+`.
  - Emits blocks with `kind="paragraph"`, `heading_path=()`, `page=None`.
  - Uses the first non-empty line as document `title` (truncated to 80 chars) or defaults to `filename`.

### 4.6 Docling Parser (`DoclingParser` - v2 Adapter)
- **Target File**: `src/ragassist/modules/knowledge/adapters/parsers/docling.py`
- **Supported MIMEs**: `("application/pdf",)`
- **Name**: `"docling"`
- **Behavior**:
  - Advanced layout analysis adapter. If `docling` is not installed, instantiation or parsing raises `ImportError` / skips under `need("knowledge.parser.docling")`.

---

## 5. Edge-Case Handling & Robustness Matrix

| Edge Case | Risk / Failure Mode | Architectural Mitigation | Contractual Verification |
|---|---|---|---|
| **Corrupted PDF** | PyMuPDF crash or segfault on corrupt binary | Validate `%PDF-` magic header; catch `fitz.FileDataError` and wrap in `ParseError`. | `ParserContract.test_corrupt_input_raises_a_parse_error` |
| **Password-Protected PDF** | Infinite retry or unhandled decrypt failure | Inspect `doc.is_encrypted`; attempt blank password `doc.authenticate("")`; raise `ParseError` on failure. | Unit test with encrypted PDF sample |
| **Empty File (0 bytes)** | `ZeroDivisionError` or index crash | If `len(content) == 0`: immediately return `ParsedDocument(title=filename, blocks=[])`. | `ParserContract.test_empty_input_gives_no_blocks_or_a_parse_error` |
| **Whitespace-only File** | Phantom empty chunks | Parser strips whitespace; if no tokens remain, returns empty `blocks = []`. | `TestPass1Structure.test_empty_blocks_are_dropped` |
| **Non-UTF-8 Encoding (Latin-1/CP1252)** | `UnicodeDecodeError` crash during text extraction | `BaseParser.safe_decode()` uses multi-tier decode (UTF-8 -> charset_normalizer -> Latin-1 -> UTF-8 replace). Never raises decode error. | `ParserContract.test_invalid_utf8_never_escapes_as_a_decode_error` |
| **Massive File (>50MB)** | Memory exhaustion (OOM), denial of service | Size check at ingress (`len(content) > 50 * 1024 * 1024`): raises `FileTooLarge`. | `UploadDocument` use case and parser ingress |
| **Malicious Scripts in HTML** | XSS / Prompt Injection via `<script>` | Strip all `<script>`, `<style>`, and `<noscript>` elements and inner contents prior to markdown conversion. | `TestHtmlStructure.test_script_content_is_dropped` |
| **Deeply Nested Headings (>6 levels)** | Stack overflow or malformed heading breadcrumbs | Cap heading levels to 6; sanitize text to single-line stripped string. | `TestMarkdownStructure.test_headings_build_the_heading_path` |
| **Malformed CSV (jagged rows)** | `IndexError` when mapping headers | Fill missing cell values with empty string `""`; truncate excess values. | `TestCsvRows.test_each_row_is_a_row_block_that_repeats_the_header` |
| **CPU Starvation on Event Loop** | Event loop freezing during PDF layout extraction | Offload all sync extraction to `run_cpu_bound()` on `_BOUNDED_EXECUTOR` (4 threads). | Event loop responsiveness under concurrent load |

---

## 6. Async/Sync Separation & `run_cpu_bound()` Offloading

The RagAssist architecture enforces asynchronous I/O and non-blocking event loop execution.
In `ragassist.shared.resilience`:
```python
_BOUNDED_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ragassist-cpu")

async def run_cpu_bound(func: Callable[..., R], *args: Any, **kwargs: Any) -> R: ...
```

In every parser:
1. The public method is `async def parse(self, content: bytes, *, mime: str, filename: str) -> ParsedDocument`.
2. The internal implementation is `def _parse_sync(self, content: bytes, mime: str, filename: str) -> ParsedDocument`.
3. The public method delegates via:
   ```python
   return await run_cpu_bound(self._parse_sync, content, mime, filename)
   ```
4. This ensures:
   - Worker concurrency is strictly bounded (max 4 concurrent CPU-heavy parses).
   - FastAPI REST endpoints, SSE streams, and health probes (`/healthz`) continue serving incoming traffic without latency spikes.

---

## 7. Concrete File Layout & Implementation Blueprint

```
src/ragassist/modules/knowledge/
├── __init__.py
├── domain/
│   ├── __init__.py                 # Exports Block, ParsedDocument, BlockKind, ParseError, UnsupportedMimeType, FileTooLarge
│   └── ast.py                      # Rich AST hierarchy (HeadingNode, TableNode, ParagraphNode, etc.)
├── application/
│   ├── __init__.py                 # Use cases: UploadDocument, ProcessIngestionJob
│   └── ports.py                    # Parser protocol, Chunker protocol, DocumentRepository port
└── adapters/
    └── parsers/
        ├── __init__.py             # Exports MarkdownParser, HtmlParser, PyMuPDFParser, TabularParser, PlainTextParser, get_parser()
        ├── base.py                 # BaseParser with run_cpu_bound() and safe_decode()
        ├── markdown.py             # MarkdownParser implementation
        ├── html.py                 # HtmlParser implementation with script/style stripping
        ├── pymupdf.py              # PyMuPDFParser (and PDFParser) with table & page extraction
        ├── tabular.py              # TabularParser (CSV/TSV with header-repeated rows)
        ├── plain_text.py           # PlainTextParser
        └── docling.py              # Optional DoclingParser v2
```

### 7.1 Parser Registry & Factory (`adapters/parsers/__init__.py`)

```python
from typing import Mapping
from .base import BaseParser
from .markdown import MarkdownParser
from .html import HtmlParser
from .pymupdf import PyMuPDFParser, PDFParser
from .tabular import TabularParser
from .plain_text import PlainTextParser
from ...domain import UnsupportedMimeType

PARSER_REGISTRY: dict[str, type[BaseParser]] = {
    "text/markdown": MarkdownParser,
    "text/x-markdown": MarkdownParser,
    "text/html": HtmlParser,
    "application/xhtml+xml": HtmlParser,
    "application/pdf": PyMuPDFParser,
    "text/csv": TabularParser,
    "text/tab-separated-values": TabularParser,
    "text/plain": PlainTextParser,
}

def get_parser(mime: str) -> BaseParser:
    """Retrieve an instantiated parser adapter for the specified MIME type."""
    cls = PARSER_REGISTRY.get(mime)
    if not cls:
        raise UnsupportedMimeType(f"No parser registered for MIME type: {mime}")
    return cls()

def default_parsers() -> Mapping[str, BaseParser]:
    """Return default dictionary of MIME -> parser instances for ingestion workers."""
    return {
        "text/markdown": MarkdownParser(),
        "text/html": HtmlParser(),
        "application/pdf": PyMuPDFParser(),
        "text/csv": TabularParser(),
        "text/plain": PlainTextParser(),
    }
```

---

## 8. Test Specification & Verification Matrix

### 8.1 Existing Contract Test Suite: `tests/unit/modules/knowledge/test_parser_contracts.py`
The implementation must pass all tests in `ParserContract`:
- `test_supports_every_declared_mime`: Validates `parser.supports(mime) == True`.
- `test_rejects_an_unrelated_mime`: Validates unknown mime returns `False`.
- `test_has_a_name`: Validates `parser.name` is non-empty string.
- `test_parsing_is_deterministic`: Multiple parses of identical content return identical `ParsedDocument`.
- `test_blocks_carry_text_and_a_heading_path`: Every block has `isinstance(block.text, str)` and `isinstance(block.heading_path, tuple)`.
- `test_unicode_text_survives_parsing`: Non-ASCII characters (`é`, `日本語`, `Café`) are preserved.
- `test_empty_input_gives_no_blocks_or_a_parse_error`: `b""` input gives `blocks == []` or raises `ParseError`.
- `test_corrupt_input_raises_a_parse_error`: `CORRUPT_PDF` raises `ParseError`.
- `test_invalid_utf8_never_escapes_as_a_decode_error`: Latin-1 encoded bytes decode or raise `ParseError`, never `UnicodeDecodeError`.

### 8.2 Existing Behavior Test Suite: `tests/unit/modules/knowledge/test_parser_behaviour.py`
- `TestMarkdownStructure`:
  - `test_headings_build_the_heading_path`: Checks `heading_path == ("Billing guide", "Invoices")`.
  - `test_a_table_is_one_table_block`: Contiguous table is single block with `kind="table"` and `| pro | 490 |`.
  - `test_a_code_fence_is_one_code_block_with_its_body`: Fenced code is `kind="code"` with body.
  - `test_markdown_has_no_page_numbers`: `all(block.page is None for block in parsed.blocks)`.
  - `test_a_heading_only_document_is_not_lost`: Solitary `# Heading` is preserved.
- `TestHtmlStructure`:
  - `test_script_content_is_dropped`: `alert('x')` is purged.
  - `test_heading_levels_build_the_heading_path`: `heading_path == ("Billing guide", "Invoices")`.
  - `test_a_table_keeps_its_cell_values`: Table block retains `pro` and `490`.
- `TestPdfPages`:
  - `test_each_page_gets_its_page_number`: Page 1 block has `page == 1`, Page 2 has `page == 2`.
  - `test_every_page_is_kept`: 6+ blocks across multiple pages, `{1, 2}.issubset(pages)`.
  - `test_a_single_page_document_has_page_one`: Single page document has `page == 1`.
- `TestCsvRows`:
  - `test_each_row_is_a_row_block_that_repeats_the_header`: `assert all("plan" in row.text and "price" in row.text for row in rows)`.
  - `test_a_quoted_comma_stays_inside_one_cell`: `"a, b"` preserved.
  - `test_a_header_only_file_has_no_rows`: `rows == []`.
  - `test_crlf_line_endings_are_handled`: `\r\n` handled cleanly.

### 8.3 Additional Edge-Case Test Suite: `tests/unit/test_parsers.py`
The implementer should add unit tests for:
1. `test_password_protected_pdf`: PDF encrypted with password raises `ParseError`.
2. `test_file_too_large`: Content > 50MB raises `FileTooLarge`.
3. `test_plain_text_parser`: `text/plain` parsed into paragraph blocks with `kind="paragraph"`.
4. `test_run_cpu_bound_offload`: Verify `run_cpu_bound` was invoked during `await parser.parse(...)` (e.g. via `unittest.mock.patch`).

---

## 9. Conclusion & Implementation Recommendations

1. **Implement Domain Entities First**:
   Add `Block`, `ParsedDocument`, `BlockKind`, `ParseError`, `UnsupportedMimeType`, `FileTooLarge`, `PasswordProtectedError` to `src/ragassist/modules/knowledge/domain/__init__.py`.
2. **Implement Base & Safe Decode**:
   Create `adapters/parsers/base.py` with `safe_decode()` and `run_cpu_bound()` integration.
3. **Implement Concrete Parsers**:
   - `markdown.py` (MarkdownParser)
   - `html.py` (HtmlParser with script stripping)
   - `pymupdf.py` (PyMuPDFParser with table and page tracking)
   - `tabular.py` (TabularParser with repeated headers)
   - `plain_text.py` (PlainTextParser)
4. **Register in `adapters/parsers/__init__.py`**:
   Expose all parsers and `get_parser()`.
5. **Verify Against Existing Test Suites**:
   Run:
   `.\.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/test_parser_contracts.py tests/unit/modules/knowledge/test_parser_behaviour.py -v`
   All 45+ contract and behavior tests will flip from `PENDING` to `PASS`.
