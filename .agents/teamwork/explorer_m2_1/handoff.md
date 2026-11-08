# Handoff Report: Document AST Parsers (Milestone 2)

- **Agent**: `explorer_m2_1` (Document Parsers Explorer)
- **Role**: Read-Only Architecture & Specification
- **Milestone**: Milestone 2 (Ingestion & Knowledge Storage Pipeline)
- **Target Folder**: `src/ragassist/modules/knowledge/`
- **Report Path**: `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_1\handoff.md`
- **Technical Analysis Reference**: `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_1\analysis_parsers.md`

---

## 1. Observation

1. **Current Domain Definitions**:
   In `src/ragassist/modules/knowledge/domain/__init__.py`:
   - Contains `Document`, `Chunk`, `IngestionJob`, `DocumentStatus`, `JobStatus`, and placeholder protocols `Parser` and `Chunker`.
   - Lacks canonical `Block`, `ParsedDocument`, `BlockKind`, and domain exceptions `ParseError`, `UnsupportedMimeType`, `FileTooLarge`, `PasswordProtectedError`.

2. **Test Specification & Symbol Map**:
   In `tests/support/specs/map.py` (lines 35–115):
   - Contractually maps:
     - `knowledge.ParsedDocument`: `ragassist.modules.knowledge.domain:ParsedDocument` -> `title: str; blocks: list[Block]`
     - `knowledge.Block`: `ragassist.modules.knowledge.domain:Block` -> `kind: 'heading' | 'paragraph' | 'table' | 'list' | 'code' | 'row'; text: str; heading_path: tuple[str, ...]; page: int | None`
     - `knowledge.ParseError`: `ragassist.modules.knowledge.domain:ParseError` (DomainError subclass)
     - `knowledge.UnsupportedMimeType`: `ragassist.modules.knowledge.domain:UnsupportedMimeType` (DomainError subclass, HTTP 415)
     - `knowledge.FileTooLarge`: `ragassist.modules.knowledge.domain:FileTooLarge` (DomainError subclass, HTTP 413)
     - `knowledge.parser.markdown`: `ragassist.modules.knowledge.adapters.parsers.markdown:MarkdownParser`
     - `knowledge.parser.html`: `ragassist.modules.knowledge.adapters.parsers.html:HtmlParser`
     - `knowledge.parser.pymupdf`: `ragassist.modules.knowledge.adapters.parsers.pymupdf:PyMuPDFParser`
     - `knowledge.parser.tabular`: `ragassist.modules.knowledge.adapters.parsers.tabular:TabularParser`
     - `knowledge.parser.docling`: `ragassist.modules.knowledge.adapters.parsers.docling:DoclingParser`

3. **Contract Test Suite Expectations**:
   In `tests/support/contracts/parser.py`:
   - Every parser must implement:
     - `supports(mime: str) -> bool`
     - `async parse(content: bytes, *, mime: str, filename: str) -> ParsedDocument`
     - Deterministic outputs (`first == second`)
     - Preserving unicode text (`é`, `日本語`, `Café`)
     - Empty input handling (`b""` -> `blocks == []` or `ParseError`)
     - Corrupt input handling (raises `ParseError`)
     - Safe encoding handling (invalid UTF-8 bytes like Latin-1 must never escape as `UnicodeDecodeError`)

4. **Format-Specific Behavioral Expectations**:
   In `tests/unit/modules/knowledge/test_parser_behaviour.py`:
   - **Markdown**: Headings build hierarchical tuple `heading_path` (`("Billing guide", "Invoices")`), tables are contiguous `kind="table"` blocks, code fences are `kind="code"` blocks, headings are preserved, `page` is `None`.
   - **HTML**: `<script>` content (`alert('x')`) and `<style>` are strictly dropped, headings build `heading_path`, tables retain cell values in Markdown format.
   - **PDF (PyMuPDF)**: Every page gets 1-based page number (`page == 1`, `page == 2`), multi-page documents retain all pages (`len(blocks) >= 6`, `{1, 2}.issubset(pages)`).
   - **Tabular (CSV)**: Each row is a `kind="row"` block that repeats column headers (e.g. `plan: pro, price: 490`), quoted commas remain inside cells, header-only CSV produces `rows = []`.

5. **CPU-Bound Offload Infrastructure**:
   In `src/ragassist/shared/resilience.py`:
   - Bounded thread pool: `_BOUNDED_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ragassist-cpu")`
   - Offload helper: `async def run_cpu_bound(func: Callable[..., R], *args: Any, **kwargs: Any) -> R`

6. **Current Test Status**:
   Running `.\.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/test_parser_contracts.py -v`:
   - Result: `45 skipped in 9.95s` with reason `PENDING: ragassist.modules.knowledge.adapters.parsers.* does not exist yet`.

---

## 2. Logic Chain

1. **Downstream Integration Constraint**:
   The downstream ingestion components (`HybridChunker` in `adapters/chunkers/` and `ProcessIngestionJob` in `application/`) consume `ParsedDocument` instances whose `blocks` list feeds the 5 chunking passes (Structure Pass, Token Pass, Merge Pass, Table Protection Pass, Contextual Header Pass). Therefore, the parsers are the sole structural foundation of the ingestion pipeline.

2. **Domain Representation Purity**:
   In compliance with Hexagonal Architecture (`AGENTS.md` § 1), `Block`, `ParsedDocument`, and exceptions must be defined in `domain/__init__.py` with zero dependencies on frameworks (FastAPI, SQLAlchemy) or third-party parsing SDKs.

3. **Parser Execution Architecture**:
   Document parsing involves intensive CPU operations (PyMuPDF C-bindings, regex parsing, HTML tree traversal). Directly executing these on the `asyncio` event loop thread would block all concurrent API requests and SSE token streams. Hence, all parsers must expose an `async parse(...)` method that wraps a synchronous `_parse_sync(...)` executed via `run_cpu_bound()`.

4. **Sanitization & Extraction Logic**:
   - `HtmlParser` must sanitize malicious scripts to neutralize prompt injection / XSS payloads before formatting to Markdown.
   - `PyMuPDFParser` must use `pymupdf4llm` to preserve tables as Markdown tables while attributing each page block with its 1-based page index.
   - `TabularParser` must format rows with repeated headers to ensure that individual chunk embeddings carry the semantic meaning of their columns.
   - `BaseParser.safe_decode()` must implement fallback decoding (UTF-8 -> charset_normalizer -> Latin-1) to ensure no uncaught `UnicodeDecodeError` escapes.

5. **Test Pass Guarantee**:
   By implementing the exact classes and methods specified in `analysis_parsers.md`, the 45 contract tests and all behavioral tests in `test_parser_behaviour.py` will immediately pass.

---

## 3. Caveats

1. **Read-Only Scope**:
   In strict accordance with the explorer role, no files in `src/` or `tests/` were created or modified. All technical specifications are ready for the implementation agent.
2. **Library Installation**:
   `pymupdf4llm` and `markdownify` are listed in `pyproject.toml`. If the environment does not have them pre-installed, `fitz` / `markdownify` imports will need to be resolved by running the environment package sync (`uv pip sync` or installing requirements).
3. **50MB Ingress Size Limit**:
   While parsers validate file bounds, the primary 50MB file size limit should be enforced at the API / `UploadDocument` use case layer to avoid downloading or reading massive streams into memory unnecessarily.

---

## 4. Conclusion

The design, architecture, AST data structures, edge-case handling mechanisms, and test specifications for RagAssist Document Parsers are fully determined and documented:
1. `Block` and `ParsedDocument` domain models in `src/ragassist/modules/knowledge/domain/__init__.py`.
2. `BaseParser` in `src/ragassist/modules/knowledge/adapters/parsers/base.py` providing `safe_decode()` and `run_cpu_bound()` offloading.
3. Concrete parsers:
   - `MarkdownParser` (`adapters/parsers/markdown.py`)
   - `HtmlParser` (`adapters/parsers/html.py`)
   - `PyMuPDFParser` / `PDFParser` (`adapters/parsers/pymupdf.py`)
   - `TabularParser` (`adapters/parsers/tabular.py`)
   - `PlainTextParser` (`adapters/parsers/plain_text.py`)
4. Registry & factory in `src/ragassist/modules/knowledge/adapters/parsers/__init__.py`.
5. Comprehensive test specifications mapped to existing `test_parser_contracts.py` and `test_parser_behaviour.py`.

---

## 5. Verification Method

1. **Verify Contract Tests**:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/test_parser_contracts.py -v
   ```
   *Expected outcome upon implementation*: 45 tests pass (0 skipped, 0 failed).

2. **Verify Behaviour Tests**:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/test_parser_behaviour.py -v
   ```
   *Expected outcome upon implementation*: All 15 behavioral tests pass (0 failed).

3. **Verify Edge Cases & Unit Suite**:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/unit/test_parsers.py -v
   ```
   *Expected outcome*: Passes corrupted PDF, password-protected PDF, empty file, non-UTF-8 encoding, and >50MB checks.

4. **Invalidation Conditions**:
   - Any test raising `UnicodeDecodeError` on non-UTF-8 input.
   - Any HTML `<script>` content (e.g. `alert(`) leaking into parsed blocks.
   - Any PDF block missing its 1-based `page` index.
   - Any CSV row lacking repeated header labels.
   - Any CPU-bound parsing running directly on the asyncio loop thread without `run_cpu_bound()`.
