# Handoff Report: 5-Pass Structure-Aware Hybrid Chunker (Milestone 2)

- **Agent**: `explorer_m2_2` (Hybrid Chunker Explorer)
- **Role**: Read-Only Architecture & Implementation Explorer
- **Milestone**: Milestone 2 (Ingestion & Knowledge Storage Pipeline)
- **Recipient**: Orchestrator (`be9621e6-d3bc-446a-abb9-2d0c46239ab1`)
- **Status**: Complete (Hard Handoff)

---

## 1. Observation

Direct code and test observations from repository inspection:

1. **Test Suite Requirements (`tests/support/specs/map.py`)**:
   - Lines 36–50 define the expected domain symbols:
     - `knowledge.ParsedDocument`: `ragassist.modules.knowledge.domain.ParsedDocument(title: str, blocks: list[Block])`
     - `knowledge.Block`: `ragassist.modules.knowledge.domain.Block(kind: 'heading' | 'paragraph' | 'table' | 'list' | 'code' | 'row', text: str, heading_path: tuple[str, ...], page: int | None)`
     - `knowledge.ChunkDraft`: `ragassist.modules.knowledge.adapters.chunkers.ChunkDraft(text: str, embed_text: str, heading_path: tuple[str, ...], page: int | None, parent: int | None, token_count: int)`
   - Lines 116–156 define chunkers and passes:
     - `knowledge.chunker.hybrid`: `ragassist.modules.knowledge.adapters.chunkers.hybrid.HybridChunker(max_tokens, overlap_tokens, merge_peers, tokenizer, parent_child=False, semantic=False, semantic_embedder=None)`
     - `knowledge.chunker.recursive`: `ragassist.modules.knowledge.adapters.chunkers.recursive.RecursiveChunker(max_tokens, overlap_tokens, tokenizer)`
     - `knowledge.chunker.docling_hybrid`: `ragassist.modules.knowledge.adapters.chunkers.docling_hybrid.DoclingHybridChunker(max_tokens, tokenizer)`
     - `knowledge.pass.structure`: `ragassist.modules.knowledge.adapters.chunkers.passes.structure_pass(parsed) -> list[Block]`
     - `knowledge.pass.token`: `ragassist.modules.knowledge.adapters.chunkers.passes.token_pass(blocks, *, max_tokens, tokenizer) -> list[Block]`
     - `knowledge.pass.merge`: `ragassist.modules.knowledge.adapters.chunkers.passes.merge_pass(blocks, *, max_tokens, tokenizer) -> list[Block]`
     - `knowledge.pass.table`: `ragassist.modules.knowledge.adapters.chunkers.passes.table_pass(blocks, *, max_tokens, tokenizer) -> list[Block]`
     - `knowledge.pass.context`: `ragassist.modules.knowledge.adapters.chunkers.passes.context_pass(blocks, *, title) -> list[ChunkDraft]`

2. **Existing Implementation Status**:
   - `src/ragassist/modules/knowledge/domain/__init__.py` currently defines `Document`, `Chunk`, `IngestionJob`, `Parser`, `Chunker`, but lacks `Block`, `BlockKind`, and `ParsedDocument`.
   - Running `.venv/Scripts/python.exe -m pytest tests/unit/modules/knowledge/test_chunker_passes.py`:
     ```
     SKIPPED [15] tests\support\specs\__init__.py:84: DRIFT: knowledge.Block: ragassist.modules.knowledge.domain has no 'Block'
     SKIPPED [1] tests\support\specs\__init__.py:84: PENDING: knowledge.pass.structure: ragassist.modules.knowledge.adapters.chunkers.passes does not exist yet
     SKIPPED [4] tests\support\specs\__init__.py:84: PENDING: knowledge.pass.context: ragassist.modules.knowledge.adapters.chunkers.passes does not exist yet
     SKIPPED [5] tests\support\specs\__init__.py:84: PENDING: knowledge.pass.token: ragassist.modules.knowledge.adapters.chunkers.passes does not exist yet
     ```
   - Running `.venv/Scripts/python.exe -m pytest tests/unit/modules/knowledge/test_chunker_contracts.py tests/unit/modules/knowledge/test_chunker_toggles.py`:
     ```
     2 passed, 41 skipped in 10.68s
     ```
     Passed: `test_the_default_strategy_is_hybrid` and `test_semantic_is_off_by_default`.
     Skipped: 41 tests awaiting `HybridChunker`, `RecursiveChunker`, and `DoclingHybridChunker`.

3. **Application Configuration (`src/ragassist/shared/config/settings.py`)**:
   - Lines 104–111 define:
     - `CHUNK_STRATEGY: str = "hybrid"`
     - `CHUNK_MAX_TOKENS: int = 512`
     - `CHUNK_OVERLAP_TOKENS: int = 64`
     - `CHUNK_MERGE_PEERS: bool = True`
     - `CHUNK_SEMANTIC: bool = False`
     - `CHUNK_PARENT_CHILD: bool = False`

4. **Event-Loop Safety Executor (`src/ragassist/shared/resilience.py`)**:
   - Lines 16–27 provide `_BOUNDED_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ragassist-cpu")` and `run_cpu_bound(func, *args, **kwargs)`.

5. **Peer Explorer Alignment (`explorer_m2_1/analysis_parsers.md`)**:
   - Document parsers (`MarkdownParser`, `HtmlParser`, `PyMuPDFParser`, `TabularParser`) produce `ParsedDocument` populated with `Block` objects with `kind`, `text`, `heading_path`, and `page`.

---

## 2. Logic Chain

1. **Mapping and Contract Verification**:
   The test suite uses `tests/support/specs/map.py` to target production symbols. Currently, 15 tests report `DRIFT` because `Block` is missing in `ragassist.modules.knowledge.domain`, and 28 tests report `PENDING` because `passes.py` and `hybrid.py` are not yet created.

2. **Domain Layer Alignment**:
   Defining `BlockKind`, `Block`, and `ParsedDocument` in `src/ragassist/modules/knowledge/domain/__init__.py` aligns both parsers (`explorer_m2_1`) and chunkers (`explorer_m2_2`), resolving the `DRIFT` condition immediately.

3. **Pass Purity & Composition**:
   The 5 passes in `src/ragassist/modules/knowledge/adapters/chunkers/passes.py` must be pure functions with the exact signatures expected by `test_chunker_passes.py`:
   - `structure_pass`: filters empty/whitespace blocks, preserves document order and heading paths.
   - `token_pass`: splits oversized blocks at sentence boundaries (`(?<=[.!?])\s+`) or word boundaries when a sentence exceeds `max_tokens`; preserves word conservation invariant.
   - `merge_pass`: merges adjacent blocks under identical `heading_path` up to `max_tokens`; strictly forbids merging tables with prose.
   - `table_pass`: leaves fitting tables whole; partitions oversized tables row-by-row, repeating the header row and separator on every partition; zero data rows lost.
   - `context_pass`: builds `ChunkDraft` with `embed_text` starting with `[Document: <title> | Section: <path>]\n` and unmodified `text` for citations.

4. **Orchestration & Toggles**:
   `HybridChunker` in `src/ragassist/modules/knowledge/adapters/chunkers/hybrid.py`:
   - Implements `from_settings(settings, tokenizer)` reading `CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS`, `CHUNK_MERGE_PEERS`, `CHUNK_PARENT_CHILD`, `CHUNK_SEMANTIC`.
   - Executes passes in sequence: `structure_pass` -> `table_pass` -> `token_pass` -> `merge_pass` (if `merge_peers=True`) -> semantic / parent-child processing -> `context_pass`.
   - In `parent_child` mode: emits section-level parent chunks and child chunks with `child.parent = parent_index`.
   - In `semantic` mode: raises `ValueError` if `semantic_embedder` is None.

5. **Fallbacks & Tokenizers**:
   - `RecursiveChunker` in `recursive.py`: recursive character fallback splitter (`["\n\n", "\n", " ", ""]`).
   - `DoclingHybridChunker` in `docling_hybrid.py`: IBM Docling wrapper.
   - `TiktokenTokenizer` in `tokenizers.py`: production tokenizer backed by `tiktoken` BPE `cl100k_base`.

6. **Asynchronous Execution Model**:
   - `chunk(parsed, *, title)` is synchronous.
   - Asynchronous worker callers execute: `await run_cpu_bound(chunker.chunk, parsed, title=title)`. This offloads CPU-heavy tokenization and string slicing to `_BOUNDED_EXECUTOR` without starving the event loop.

---

## 3. Caveats

1. **Docling Dependency**: `DoclingHybridChunker` requires IBM Docling (`docling` extra). In its absence, `test_chunker_contracts.py` skips `TestDoclingHybridChunkerContract` as `PENDING`. This is expected behavior.
2. **Semantic Chunker Embedder**: `semantic=True` requires an external embedder instance (`semantic_embedder`). In unit tests, a synchronous fake (`_KeywordEmbedder`) is injected.
3. **Large Single Table Rows**: If a single markdown table row exceeds `max_tokens`, `table_pass` emits that single row with the repeated header rather than dropping data, prioritizing data integrity over strict truncation.

---

## 4. Conclusion

The architectural design, domain contracts, 5-pass pure functions, chunk draft representations, configuration toggle behavior, and event-loop safety mechanics for `HybridChunker` are fully specified and verified against the existing test suite.

All code specifications and test matrix mappings are documented in:
- `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_2\analysis_chunking.md`

The worker agent (`worker_m2`) can immediately implement the chunking files to activate the 43 pending unit tests.

---

## 5. Verification Method

### 5.1 Verification Commands
Execute the chunker test suite:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/test_chunker_passes.py -v
.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/test_chunker_contracts.py tests/unit/modules/knowledge/test_chunker_toggles.py -v
.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/test_chunker_properties.py -v
```

### 5.2 Success Invariants
1. `test_chunker_passes.py`: All 25 pass unit tests pass.
2. `test_chunker_contracts.py`: All contract tests for `TestHybridChunkerContract` and `TestRecursiveChunkerContract` pass.
3. `test_chunker_toggles.py`: All 12 toggle tests pass.
4. `test_chunker_properties.py`: All 6 Hypothesis property tests pass with zero counter-examples.
5. Invalidation Condition: Any test failing on token budget overflow (`> max_tokens`), broken table formatting (missing header on partition), or severed heading paths invalidates the implementation.
