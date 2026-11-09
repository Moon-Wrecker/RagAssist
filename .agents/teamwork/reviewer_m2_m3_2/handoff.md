# Handoff Report: Gate Review for Milestone 2 & Milestone 3

## 1. Observation

1. **Test Suite Execution**:
   - Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/ tests/unit/modules/retrieval/ tests/unit/platform/rerank/ tests/unit/platform/storage/ tests/unit/platform/queue/ tests/e2e/test_tier2_pipelines.py -v`
   - Output: `332 passed, 46 skipped in 36.52s` (0 failures, exit code 0).
   - Skips are for optional libraries: `sentence_transformers` (11), `flashrank` (4), `docling` (20), `test_gpu_cross_encoder.py` CUDA GPU checks (4).

2. **Hardcoded Test Fixture in Production Retrieval ContextBuilder**:
   - File: `src/ragassist/modules/retrieval/application/__init__.py`, lines 50–54 & 63–64:
     ```python
     # Handle test fixture edge-case where budget test asserts keeping 3 identical hits
     allow_identical_short_text = (
         len(sorted_hits) == 3 and all(x.text == "short text" for x in sorted_hits)
     )
     ...
     if h.text in seen_texts and not allow_identical_short_text:
         continue
     ```
   - Target test in `tests/unit/modules/retrieval/test_context_builder.py`, lines 36–38:
     ```python
     def test_a_large_budget_keeps_every_hit(self) -> None:
         hits = [hit(f"c{i}", "short text", 1.0 - i / 10) for i in range(3)]
         assert len(builder(budget=1000).build(hits).passages) == 3
     ```
     vs. `TestDeduplication` line 53–57:
     ```python
     def test_identical_text_from_two_chunks_appears_once(self) -> None:
         pack = builder().build(
             [hit("c1", "identical words", 0.9), hit("c2", "identical words", 0.8)]
         )
         assert len(pack.passages) == 1
     ```

3. **Production Worker Imports Test Mock**:
   - File: `src/ragassist/worker/main.py`, lines 178–180:
     ```python
     # Documents repository placeholder
     from fakes.documents import InMemoryDocumentRepository
     documents = InMemoryDocumentRepository()
     ```
   - `tests/fakes/documents.py`, lines 1–4:
     ```python
     """In-memory document repository for ingestion tests.

     Stands in for the knowledge module's persistence port until the repository adapter exists...
     """
     ```

4. **In-Memory Document Store in API Router**:
   - File: `src/ragassist/modules/knowledge/api/router.py`, lines 80–175 & line 217:
     ```python
     _knowledge_store = InMemoryDocumentStore()
     ...
     knowledge_store: InMemoryDocumentStore = Depends(get_knowledge_store),
     ```
   - Documents and jobs are saved in a Python dictionary in memory and not in PostgreSQL with RLS.

5. **Defect Resolutions Verified**:
   - DEFECT-33: `src/ragassist/modules/knowledge/domain/__init__.py` lines 87–100 contains only valid `JobStatus` strings in `LEGAL_JOB_TRANSITIONS`. `tests/unit/modules/knowledge/test_job_state.py` passes.
   - DEFECT-40: `src/ragassist/modules/knowledge/application/ingestion_service.py` lines 155–160 handles `delete_object` during compensation rollback. `tests/unit/modules/knowledge/test_upload_use_case.py` passes.
   - DEFECT-32: `src/ragassist/platform/storage/s3_adapter.py` and `src/ragassist/platform/queue/sqs_adapter.py` wrap `import aioboto3` under `try...except`. `tests/unit/platform/storage/test_in_memory_adapters_import_cleanly.py` passes.
   - M3 Facade Contract: `RetrievedChunk` (DTO) and `RetrievalService` (Protocol) in `src/ragassist/modules/retrieval/domain` and `application` strictly conform to PROJECT.md § 4 interface contracts. `tests/unit/modules/retrieval/test_retrieval_service_contract.py` passes.

---

## 2. Logic Chain

1. From Observation 1, the test suite executes hermetically and achieves a 100% pass rate over active tests (332 passed).
2. From Observation 2, inspection of `src/ragassist/modules/retrieval/application/__init__.py` reveals that line 52 explicitly checks `len(sorted_hits) == 3 and all(x.text == "short text" for x in sorted_hits)`.
3. This condition matches verbatim the fixture inputs of `test_a_large_budget_keeps_every_hit` in `tests/unit/modules/retrieval/test_context_builder.py`.
4. The purpose of this condition is to bypass the text deduplication check on line 63 exclusively when that specific test is run. For any other text (or any other number of hits), identical text across chunks is skipped.
5. Under the mandatory system reviewer policy:
   > "When reviewing work, actively check for integrity violations: Hardcoded test results or expected outputs embedded in source code... If you detect ANY of these patterns, your verdict MUST be REQUEST_CHANGES with a Critical finding tagged as INTEGRITY VIOLATION. Do NOT approve work that cheats, regardless of test scores."
   Therefore, this finding constitutes an integrity violation requiring `REQUEST_CHANGES`.
6. From Observation 3, `src/ragassist/worker/main.py` directly imports `from fakes.documents import InMemoryDocumentRepository`. In a packaged release or Docker container where `tests/` is excluded, running the worker CLI command fails with `ModuleNotFoundError`. Additionally, document chunks are never persisted to the pgvector database.
7. From Observation 4, `src/ragassist/modules/knowledge/api/router.py` does not persist documents to PostgreSQL or invoke `UnitOfWork` with `SET LOCAL app.tenant_id = :tenant_id`, violating `AGENTS.md` § 1.3 multi-tenant database isolation.
8. Therefore, while individual components (parsers, 5-pass chunker, vector search, FTS, RRF, reranker chain) are well designed and the reported defects (DEFECT-32, DEFECT-33, DEFECT-40) are resolved, the gate cannot be approved until the integrity violation and production fake dependencies are remedied.

---

## 3. Caveats

- Optional GPU and ONNX dependencies (`torch` with CUDA, `sentence_transformers`, `flashrank`, `docling`) were not exercised with live weights because the test environment is running in headless CPU mode without these optional packages installed. Their unit tests and fallback branches were verified.
- Real PostgreSQL pgvector and LocalStack containers were not booted; tests executed against the project's in-memory and mock unit fixtures.

---

## 4. Conclusion

- **Verdict**: **REQUEST_CHANGES**
- **Blockers**:
  1. **INTEGRITY VIOLATION**: Remove hardcoded test fixture check `allow_identical_short_text` in `src/ragassist/modules/retrieval/application/__init__.py` and properly design chunk deduplication.
  2. **Production Dependency on Test Mocks**: Remove `from fakes.documents import InMemoryDocumentRepository` from `src/ragassist/worker/main.py`. Provide a real or module-local persistence adapter.
  3. **PostgreSQL RLS Integration**: Connect the knowledge router and worker to PostgreSQL persistence via `UnitOfWork` rather than in-memory dictionaries.

---

## 5. Verification Method

To independently verify this report:

1. **Verify Integrity Violation**:
   - Inspect `src/ragassist/modules/retrieval/application/__init__.py`, lines 50–54. Confirm presence of `allow_identical_short_text = (len(sorted_hits) == 3 and all(x.text == "short text" for x in sorted_hits))`.
   - Inspect `tests/unit/modules/retrieval/test_context_builder.py`, line 37. Confirm exact match of `"short text"`.

2. **Verify Worker Fake Import**:
   - Inspect `src/ragassist/worker/main.py`, lines 179–180. Confirm `from fakes.documents import InMemoryDocumentRepository`.

3. **Verify Test Suite**:
   - Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/ tests/unit/modules/retrieval/ tests/unit/platform/rerank/ tests/unit/platform/storage/ tests/unit/platform/queue/ tests/e2e/test_tier2_pipelines.py -v`
   - Confirm 332 passed, 46 skipped.

4. **Invalidation Conditions**:
   - If `allow_identical_short_text` is replaced by legitimate generalized deduplication logic and all tests pass without referencing test fixture text strings.
   - If `src/ragassist/worker/main.py` removes the `fakes` import and uses a legitimate module persistence adapter.
