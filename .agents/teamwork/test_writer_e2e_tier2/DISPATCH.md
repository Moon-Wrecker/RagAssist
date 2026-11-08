# DISPATCH — test_writer_e2e_tier2

- **Role**: E2E Test Writer (Tier 2: Pipeline & Workflow Integration)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier2
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md

## Exclusive Write Ownership
You have exclusive write ownership over:
- `tests/e2e/test_tier2_pipelines.py`
- `tests/support/` (test helpers, fakes, data generators)
- `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier2\`

DO NOT modify files in `src/ragassist/` (source code is owned exclusively by builders).

## Task Instructions
1. Read `TEST_INFRA.md` § 2.1 (Tier 2 definition), § 3 (Features 11, 12, 13, 14, 15, 16, 17, 18, 24, 25, 27).
2. Read existing `tests/e2e/conftest.py` and `tests/e2e/test_tier1_features.py` to match testing idioms, fixtures, and assertion styles.
3. Implement `tests/e2e/test_tier2_pipelines.py` specifying opaque-box contractual integration tests for:
   - Ingestion Pipeline: Document parsing (PDF/HTML/MD/text) -> 5-pass hybrid chunking -> vector embedding -> database storage.
   - Retrieval Pipeline: Dense vector cosine search + Sparse PostgreSQL FTS -> RRF fusion (k=60) -> toggleable reranker (Cross-Encoder -> FlashRank -> None) -> candidate relevance grading.
   - LangGraph Agent Workflow: Intent classification -> retrieval -> grading -> query rewriting loop -> SaaS tool execution -> grounded answer synthesis with citation tags.
   - Checkpointer: Thread state checkpointing scoped to `{tenant_id}:{conversation_id}`.
4. Use standard pytest conventions with async test support (`pytest-asyncio`). Use mocks/fakes where live infrastructure or builders are pending so tests can run cleanly or act as contracts for builders.
5. Execute test verification using `BypassSandbox=True`.
6. Write `handoff.md` in `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier2\`.
7. Send a message to orchestrator upon completion.


## 2026-11-08T09:07:44Z
You are test_writer_e2e_tier2 (E2E Test Writer for Tier 2: Pipeline & Workflow Integration) for project RagAssist.
CRITICAL INSTRUCTIONS:
1. You MUST read the original user request at:
   `d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md`
   before beginning work.
2. Read `d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md`, `d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md`, and `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier2\DISPATCH.md`.
3. Check existing files in:
   - `tests/e2e/conftest.py`
   - `tests/e2e/test_tier1_features.py`
4. Your exclusive write ownership is:
   - `tests/e2e/test_tier2_pipelines.py`
   - `tests/support/`
   DO NOT modify files in `src/` (implementation code is owned by builders).
5. Test Design Requirements for Tier 2 (`test_tier2_pipelines.py`):
   - Design at least 25-30 rigorous opaque-box contractual integration tests covering Ingestion, Retrieval, LangGraph workflow & Agent pipelines.
