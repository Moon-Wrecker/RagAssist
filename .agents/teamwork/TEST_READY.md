# E2E Test Suite Ready

## Test Runner
- Full Test Suite Execution Command:
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/e2e -v
  ```
- Individual Tier Commands:
  - **Tier 1 (Foundations & Core Contracts)**:
    ```powershell
    .\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier1_features.py -v
    ```
  - **Tier 2 (Pipeline & Workflow Integration)**:
    ```powershell
    .\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier2_pipelines.py -v
    ```
  - **Tier 3 (Multi-Tenant Boundary & Security Isolation)**:
    ```powershell
    .\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier3_isolation.py -v
    ```
  - **Tier 4 (Production Surface, Streaming & Observability)**:
    ```powershell
    .\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier4_production.py -v
    ```
- Expected Result: All active suites execute hermetically offline with 100% pass rate (162 passing tests, 1 expected xfail, 0 failures, exit code 0).

---

## Coverage Summary

| Tier | Test File | Test Count | Pass Rate | Execution Time | Key Scope |
|------|-----------|-----------:|:---------:|:--------------:|-----------|
| **Tier 1** | `tests/e2e/test_tier1_features.py` | 30 | 100% (30/30) | ~9.00s | Hexagonal domain models, JWT Principal, UnitOfWork RLS context, Provider registries, FallbackChain, Bounded CPU executor, Chat model capabilities & pricing, Embedding protocols, 5-pass hybrid chunking heuristics, Reciprocal Rank Fusion ($k=60$), System One decision protocols (Route, Guard, Grade, Ground), Mock SaaS client endpoints. |
| **Tier 2** | `tests/e2e/test_tier2_pipelines.py` | 35 | 100% (35/35) | ~5.05s | End-to-end ingestion pipeline (PDF/HTML/MD parsing), 5-pass structure-aware hybrid chunking (AST pass, sentence splitting, sibling merging, table splitting with repeated headers, breadcrumbs), S3 tenant scoping, Ingestion worker idempotency & atomic chunk replacement, Dense pgvector search, Sparse FTS tsvector search, RRF $k=60$ fusion, Toggleable reranker cascade (Cross-Encoder -> FlashRank -> NoOp), LangGraph cyclic state machine workflow, `{tenant_id}:{conversation_id}` checkpointer isolation, Citation assembler, Human escalation trigger (< 0.65). |
| **Tier 3** | `tests/e2e/test_tier3_isolation.py` | 58 | 100% (58/58) | ~4.97s | Cross-tenant data isolation, PostgreSQL Row-Level Security (`SET LOCAL app.tenant_id = :id`), JWT cryptographic tampering rejection, Algorithm "none" denial, Expired token handling, Role-based access control (RBAC), Approval policy for mutating SaaS tools, Audit logging with Principal claim extraction & secret masking, Prompt injection guardrails (zero-width character stripping, Cyrillic/Greek homoglyphs, DAN mode jailbreaks), Fail-closed decider crash handling. |
| **Tier 4** | `tests/e2e/test_tier4_production.py` | 40 | 100% (39 pass, 1 xfail) | ~1.30s | Conversation lifecycle REST endpoints (`/v1/conversations`), Server-Sent Events (SSE) streaming protocol (`docs/api/sse-contract.md`), Token chunk reassembly, Citation schemas, Tool call events, Terminal `done` event, Graceful error handling (`event: error`), Multipart file upload (`POST /v1/documents`), S3 tenant partitioning, SQS dispatch, Prometheus `/metrics` instrumentation, LangSmith tracing toggle & credential redaction, RAG Triad benchmark runner (Faithfulness, Answer Relevance, Context Precision). |
| **Total** | **All 4 Tiers** | **163** | **100% (162 passed, 1 xfail, 0 failed)** | **~20s** | **Complete coverage across all 34 features in PROJECT.md.** |

---

## Feature Checklist Across All 4 Tiers

| # | Feature Name | Milestone | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Status |
|---|--------------|:---------:|:------:|:------:|:------:|:------:|:------:|
| 1 | Modular Monolith & Hexagonal Layering | M1 | ✓ (5) | ✓ | ✓ | ✓ | VERIFIED |
| 2 | Tenant Row-Level Security (RLS) | M2 | — | ✓ | ✓ (12) | — | VERIFIED |
| 3 | UnitOfWork RLS Session Context | M1 | ✓ (3) | ✓ | ✓ (8) | — | VERIFIED |
| 4 | JWT Principal Authentication | M1 | ✓ (3) | — | ✓ (15) | ✓ | VERIFIED |
| 5 | Generic Provider Registry | M1 | ✓ (3) | — | — | — | VERIFIED |
| 6 | Automatic Fallback Chain | M1 | ✓ (3) | ✓ | — | — | VERIFIED |
| 7 | Event-Loop Bounded CPU Executor | M1 | ✓ (2) | ✓ | — | — | VERIFIED |
| 8 | Swappable Chat Model Providers | M1 | ✓ (3) | — | — | — | VERIFIED |
| 9 | Model Capabilities & Token Pricing | M1 | ✓ (2) | — | — | — | VERIFIED |
| 10 | Dense Embedding Providers | M1 | ✓ (2) | ✓ | — | — | VERIFIED |
| 11 | Multi-Format Document Parsing | M2 | — | ✓ (5) | — | ✓ | VERIFIED |
| 12 | 5-Pass Structure-Aware Hybrid Chunking | M2 | ✓ (1) | ✓ (6) | — | — | VERIFIED |
| 13 | S3 Storage & SQS Ingestion Queue | M2 | — | ✓ (3) | — | ✓ | VERIFIED |
| 14 | Background Ingestion Worker | M2 | — | ✓ (4) | — | — | VERIFIED |
| 15 | Dense Vector Search with Iterative Scan | M3 | — | ✓ (3) | ✓ | — | VERIFIED |
| 16 | Sparse Full-Text Search | M3 | — | ✓ (3) | — | — | VERIFIED |
| 17 | Reciprocal Rank Fusion (RRF $k=60$) | M3 | ✓ (1) | ✓ (3) | — | — | VERIFIED |
| 18 | Toggleable Reranker Chain | M3 | — | ✓ (4) | — | — | VERIFIED |
| 19 | Decision Layer First Architecture | M1 | ✓ (2) | — | — | — | VERIFIED |
| 20 | Query Intent Router | M1 | ✓ (1) | ✓ | — | — | VERIFIED |
| 21 | Input Safety & Prompt Injection Guard | M1 | ✓ (1) | ✓ | ✓ (15) | — | VERIFIED |
| 22 | Chunk Relevance Grader | M1 | ✓ (1) | ✓ | — | — | VERIFIED |
| 23 | Grounding & Hallucination Judge | M1 | ✓ (1) | — | ✓ (3) | — | VERIFIED |
| 24 | LangGraph State Machine Workflow | M4 | — | ✓ (4) | — | — | VERIFIED |
| 25 | Persistent Conversation Checkpointer | M4 | — | ✓ (2) | ✓ (5) | — | VERIFIED |
| 26 | Mock SaaS Integration Tools & RBAC | M4 | ✓ (5) | ✓ | ✓ (10) | — | VERIFIED |
| 27 | Citation & Provenance Assembler | M4 | — | ✓ (2) | — | ✓ | VERIFIED |
| 28 | Conversation Lifecycle Endpoints | M5 | — | — | — | ✓ (7) | VERIFIED |
| 29 | Server-Sent Events (SSE) Streaming | M5 | — | — | — | ✓ (10) | VERIFIED |
| 30 | Document Ingestion Upload Endpoint | M2 | — | — | — | ✓ (7) | VERIFIED |
| 31 | Human Escalation Trigger (< 0.65) | M4 | ✓ (1) | ✓ (2) | — | — | VERIFIED |
| 32 | Prometheus Metrics Instrumentation | M5 | — | — | — | ✓ (5) | VERIFIED |
| 33 | LangSmith Distributed Tracing Switch | M5 | — | — | — | ✓ (5) | VERIFIED |
| 34 | RAG Triad Benchmark Runner | M5 | — | — | — | ✓ (6) | VERIFIED |
