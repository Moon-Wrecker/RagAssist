# TEST_INFRA.md — End-to-End (E2E) Test Architecture & Specification

## 1. Test Philosophy & Design Principles

### 1.1 Opaque-Box, Requirement-Driven Testing
The E2E Test Suite for **RagAssist** is built on an **opaque-box, requirement-driven methodology**. Test specifications are strictly derived from the contractual requirements defined in `ORIGINAL_REQUEST.md`, `PROJECT.md` § Feature Inventory, and the repository architecture standards in `AGENTS.md`.

- **No Internal Coupling**: Tests do not couple to transient internal private functions, unexported helper utilities, or internal module refactorings. Tests interact with public interface protocols (`ChatModelProvider`, `EmbeddingProvider`, `Decider`, `RetrievalService`), FastAPI HTTP endpoints, SSE event streams, and database transaction contracts.
- **Contract Fidelity**: Every assertion verifies a documented invariant (e.g., tenant ID propagation, RLS session variable scoping, JSON claim schemas, fallback order execution, bounded pool thread offload, or SaaS REST payload integrity).
- **Behavioral Grounding**: Expected outputs are derived directly from specification definitions, mathematical properties (e.g., RRF scoring formula $RRF\_Score = \sum \frac{1}{60 + rank}$), and deterministic state machine transitions.

### 1.2 Isolation & Progressive Testability
- **Hermetic Test Isolation**: Every test case initializes its own state, seeds unique tenant/user identifiers (`uuid4`), and executes independently of test execution order.
- **Zero State Leakage**: Database operations execute inside transactional boundaries (`UnitOfWork`) that roll back or isolate tenant settings (`SET LOCAL app.tenant_id = :tid, true`).
- **Deterministic Offline Execution**: External network dependencies (OpenAI, Anthropic, AWS S3, AWS SQS, SaaS webhooks) are satisfied through realistic, spec-compliant in-memory fakes and HTTP transport shims (`httpx.ASGITransport` connecting directly to `services.mock_saas.main.app`), enabling fast local execution without external network connectivity.
- **Progressive Milestone Alignment**: Tier 1 tests are executable against early milestone features (M1 foundation: security, resilience, provider registries, decision layer, chunking heuristics, mock SaaS). Successive tiers (Tier 2 through Tier 4) cover composite pipelines, multi-tenant boundaries, and public API surfaces.

---

## 2. 4-Tier Test Architecture

The E2E test suite is organized into four hierarchical verification tiers:

```
┌────────────────────────────────────────────────────────────────────────┐
│             Tier 4: Production Surface, Streaming & Resilience         │
│             - REST API Endpoints (/v1/conversations, /auth)            │
│             - Server-Sent Events (SSE) Contract & Lifecycles           │
│             - Provider Outage Failover & Observability (/metrics)      │
├────────────────────────────────────────────────────────────────────────┤
│             Tier 3: Multi-Tenant Boundary & Security Isolation         │
│             - Cross-Tenant Data Leakage Prevention (Row-Level Security) │
│             - JWT Tampering, Expiration & Invalid Claim Rejection      │
│             - Role-Based Access Control (Admin vs User vs Agent)       │
│             - Prompt Injection & Toxic Content Neutralization          │
├────────────────────────────────────────────────────────────────────────┤
│             Tier 2: Pipeline & Workflow Integration                    │
│             - End-to-End Document Ingestion & Chunk Indexing Pipeline   │
│             - Hybrid Retrieval (Dense pgvector + Sparse FTS + RRF)     │
│             - LangGraph Cyclical State Machine & PostgreSQL Checkpoints│
│             - Citation & Provenance Assembly                           │
├────────────────────────────────────────────────────────────────────────┤
│             Tier 1: Foundation & Core Contracts (Happy Paths)          │
│             - JWT Principal Encoding & Decoding                        │
│             - UnitOfWork RLS Session Context & Transaction Control     │
│             - Provider Registry & FallbackChain Execution              │
│             - Chat Model Capabilities & Pricing Inspection             │
│             - Structure-Aware Document Chunking & Table Protection     │
│             - Decision Layer Contracts (Route, Guard, Grade, Ground)   │
│             - Mock SaaS Client Tool Endpoints (Accounts, Tickets)      │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Tier Definitions

1. **Tier 1 — Foundation & Core Contracts (Happy Paths)**:
   - Validates that foundational domain models, value objects, cryptographic token operations, provider registries, fallback chains, decision protocols, chunker heuristics, and external service contracts behave according to specifications under expected valid inputs.
2. **Tier 2 — Pipeline & Workflow Integration**:
   - Validates end-to-end multi-component sequences:
     - Ingestion pipeline: Raw document parsing -> 5-pass hybrid chunking -> vector embedding -> database storage.
     - Retrieval pipeline: Query embedding -> dense similarity search + sparse PostgreSQL FTS -> RRF fusion ($k=60$) -> reranking -> candidate relevance grading.
     - LangGraph Agent workflow: Intent classification -> retrieval -> grading -> rewriting -> tool invocation -> answer synthesis with citations.
3. **Tier 3 — Multi-Tenant Boundary & Security Isolation**:
   - Adversarial verification of tenant isolation and security boundaries:
     - Cross-tenant data isolation: Ensuring Tenant A queries cannot view Tenant B documents, chunks, conversations, or checkpoints under any query permutation.
     - Row-Level Security verification: Verifying that `SET LOCAL app.tenant_id` prevents data access across connection pool reuse.
     - Auth security: Rejection of forged JWTs, expired signatures, missing claims, and unauthorized role escalations.
     - Guardrail safety: Prompt injection and adversarial payload filtering.
4. **Tier 4 — Production Surface, Streaming & Resilience**:
   - Validates public-facing HTTP contracts, real-time token streaming via Server-Sent Events (SSE), resilience under simulated provider downtime, and Prometheus instrumentation.

---

## 3. Comprehensive Feature Coverage Matrix (34 Features)

Below is the complete enumeration and mapping of all 34 features from `PROJECT.md` § Feature Inventory across the 4 test tiers:

| # | Feature Name | Milestone | Tier | Target Test Module | Verification Strategy |
|---|--------------|-----------|------|--------------------|-----------------------|
| 1 | Modular Monolith & Hexagonal Layering | M1 | Tier 1 | `test_tier1_features.py` | Verify import layer separation; domain entities have no dependencies on adapters or frameworks. |
| 2 | Tenant Row-Level Security (RLS) | M2 | Tier 3 | `test_tier3_isolation.py` | Verify PostgreSQL RLS rules enforce zero cross-tenant row leakage across concurrent sessions. |
| 3 | UnitOfWork RLS Session Context | M1 | Tier 1 | `test_tier1_features.py` | Verify `UnitOfWork` executes `SET LOCAL app.tenant_id = :id` within transaction and rolls back on failure. |
| 4 | JWT Principal Authentication | M1 | Tier 1 | `test_tier1_features.py` | Test `create_access_token` and `decode_access_token` with tenant_id, user_id, role, and expiration claims. |
| 5 | Generic Provider Registry | M1 | Tier 1 | `test_tier1_features.py` | Verify thread-safe registration, factory lookup, normalization, and error handling for unknown providers. |
| 6 | Automatic Fallback Chain | M1 | Tier 1 | `test_tier1_features.py` | Verify sequential provider execution, failure skipping, acceptance condition checks, and error exhaustion. |
| 7 | Event-Loop Bounded CPU Executor | M1 | Tier 1 | `test_tier1_features.py` | Verify `run_cpu_bound()` offloads CPU-heavy work to thread pool without blocking asyncio event loop. |
| 8 | Swappable Chat Model Providers | M1 | Tier 1 | `test_tier1_features.py` | Verify `ChatModelProvider` protocol compliance across OpenAI, Anthropic, and OpenRouter adapters. |
| 9 | Model Capabilities & Token Pricing | M1 | Tier 1 | `test_tier1_features.py` | Verify capability introspection (context window, tool support, streaming) and token pricing calculation. |
| 10 | Dense Embedding Providers | M1 | Tier 1 | `test_tier1_features.py` | Verify `EmbeddingProvider` protocol compliance, vector dimension reporting, and query/document embedding. |
| 11 | Multi-Format Document Parsing | M2 | Tier 2 | `test_tier2_pipelines.py` | Verify PDF (PyMuPDF4LLM) and HTML (markdownify) parsers preserve tables, headers, and metadata. |
| 12 | 5-Pass Structure-Aware Hybrid Chunking | M2 | Tier 1 / Tier 2 | `test_tier1_features.py`, `test_tier2_pipelines.py` | Verify table preservation, heading breadcrumb propagation, token bounds, and peer chunk merging. |
| 13 | S3 Storage & SQS Ingestion Queue | M2 | Tier 2 | `test_tier2_pipelines.py` | Verify raw document storage in S3 bucket and asynchronous ingest event publishing to SQS queue. |
| 14 | Background Ingestion Worker | M2 | Tier 2 | `test_tier2_pipelines.py` | Verify async ingestion worker dequeues SQS message, downloads S3 object, chunks, embeds, and persists. |
| 15 | Dense Vector Search with Iterative Scan | M3 | Tier 2 | `test_tier2_pipelines.py` | Verify pgvector cosine distance search with `relaxed_order` and top_k result filtering. |
| 16 | Sparse Full-Text Search | M3 | Tier 2 | `test_tier2_pipelines.py` | Verify PostgreSQL tsvector search with `websearch_to_tsquery` for exact keyword and phrase matches. |
| 17 | Reciprocal Rank Fusion (RRF) | M3 | Tier 1 / Tier 2 | `test_tier1_features.py`, `test_tier2_pipelines.py` | Verify mathematical calculation of RRF score ($k=60$) combining dense and sparse rank lists. |
| 18 | Toggleable Reranker Chain | M3 | Tier 2 | `test_tier2_pipelines.py` | Verify reranker cascade: Cross-Encoder (GPU) -> FlashRank (CPU ONNX) -> None (fallback to RRF order). |
| 19 | Decision Layer First Architecture | M1 | Tier 1 | `test_tier1_features.py` | Verify System One decision interface evaluating routing, safety, grading, and grounding contracts. |
| 20 | Query Intent Router | M1 | Tier 1 | `test_tier1_features.py` | Verify intent classification into `rag_search`, `saas_action`, `general_chat`, `human_escalation`. |
| 21 | Input Safety & Prompt Injection Guard | M1 | Tier 1 / Tier 3 | `test_tier1_features.py`, `test_tier3_isolation.py` | Verify detection of prompt injection, jailbreak strings, and toxicity with safety verdict schema. |
| 22 | Chunk Relevance Grader | M1 | Tier 1 | `test_tier1_features.py` | Verify relevance score filtering of candidate chunks to eliminate non-relevant content. |
| 23 | Grounding & Hallucination Judge | M1 | Tier 1 | `test_tier1_features.py` | Verify evaluation of synthesized answers against cited context chunks to detect ungrounded claims. |
| 24 | LangGraph State Machine Workflow | M4 | Tier 2 | `test_tier2_pipelines.py` | Verify cyclic graph execution: router -> retrieval -> grade -> rewrite -> tools -> synthesis. |
| 25 | Persistent Conversation Checkpointer | M4 | Tier 2 | `test_tier2_pipelines.py` | Verify thread state checkpointing in PostgreSQL scoped strictly to `{tenant_id}:{conversation_id}`. |
| 26 | Mock SaaS Integration Tools | M4 | Tier 1 | `test_tier1_features.py` | Verify Mock SaaS client HTTP calls: overview, subscription, invoices, update email, create ticket. |
| 27 | Citation & Provenance Assembler | M4 | Tier 2 | `test_tier2_pipelines.py` | Verify assembly of source citations with document title, page number, and section breadcrumbs. |
| 28 | Conversation Lifecycle Endpoints | M5 | Tier 4 | `test_tier4_production.py` | Verify REST API endpoints: create conversation, list conversations, fetch thread history. |
| 29 | Server-Sent Events (SSE) Streaming | M5 | Tier 4 | `test_tier4_production.py` | Verify SSE event stream lifecycle: `token` events, `source` citation events, and `done` termination. |
| 30 | Document Ingestion Upload Endpoint | M2 | Tier 4 | `test_tier4_production.py` | Verify multipart file upload streaming to S3 and dispatching SQS ingest message with 202 Accepted. |
| 31 | Human Escalation Trigger | M4 | Tier 1 / Tier 3 | `test_tier1_features.py`, `test_tier3_isolation.py` | Verify escalation gating when confidence < `ESCALATION_THRESHOLD` (0.65) creates support ticket. |
| 32 | Prometheus Metrics Instrumentation | M5 | Tier 4 | `test_tier4_production.py` | Verify `/metrics` endpoint exposes HTTP latency, request count, and token usage metrics. |
| 33 | LangSmith Tracing Switch | M5 | Tier 4 | `test_tier4_production.py` | Verify tracing flags properly enable or disable LangSmith callback handlers without error. |
| 34 | RAG Triad Benchmark Runner | M5 | Tier 4 | `test_tier4_production.py` | Verify automated evaluation runner calculating faithfulness, answer relevance, and context precision. |

---

## 4. Test Framework & Directory Layout

### 4.1 Layout
```
tests/e2e/
├── __init__.py                  # Package marker
├── conftest.py                  # Core fixtures: tokens, HTTP client shims, fake db/UOW, fake vectors
├── test_tier1_features.py       # Tier 1: Foundation & Core Contracts (Happy Paths)
├── test_tier2_pipelines.py      # Tier 2: Ingestion, Retrieval & Agent Pipelines
├── test_tier3_isolation.py      # Tier 3: Multi-Tenant Boundary & Security Isolation
└── test_tier4_production.py     # Tier 4: Production Surface, Streaming & Observability
```

### 4.2 Shared Test Fixtures (`conftest.py`)
- `tenant_factory`: Creates mock tenant identifiers and user IDs.
- `tenant_tokens`: Pre-generates valid JWT bearer tokens for standard user, admin, and agent roles.
- `mock_saas_client`: In-memory `httpx.AsyncClient` backed by `httpx.ASGITransport(app=mock_saas_app)`, enabling full HTTP verification of Mock SaaS endpoints without network sockets.
- `fake_uow_factory`: In-memory `UnitOfWork` test double validating transactional semantics and RLS context variable management (`SET LOCAL app.tenant_id = :id`).
- `in_memory_vector_store`: Memory-backed vector index implementing cosine distance ranking and metadata filtering.
- `fake_provider_registry`: Standardized registry pre-seeded with test providers and fallback chains.

---

## 5. Test Runner & Execution Semantics

### 5.1 Commands
- **Full E2E Suite**:
  ```bash
  pytest tests/e2e -v
  ```
- **Tier 1 Only (Foundation & Core Contracts)**:
  ```bash
  pytest tests/e2e/test_tier1_features.py -v
  ```
- **Tier 2 Only (Pipelines & Workflows)**:
  ```bash
  pytest tests/e2e/test_tier2_pipelines.py -v
  ```
- **Tier 3 Only (Isolation & Security)**:
  ```bash
  pytest tests/e2e/test_tier3_isolation.py -v
  ```
- **Tier 4 Only (Production Surface & SSE)**:
  ```bash
  pytest tests/e2e/test_tier4_production.py -v
  ```

### 5.2 Pass / Fail Semantics
- **Exit Code 0**: 100% test pass rate. Zero unexpected exceptions, failed assertions, or unresolved async tasks.
- **Failures**: Any deviation from specification contracts (e.g. status code mismatch, missing claim, RLS leak, incorrect RRF score) immediately fails the test and prints diagnostic failure output.
- **No Flakiness**: All timing-dependent logic uses explicit asyncio primitives or mocked virtual time.

---

## 6. Test Suite Execution & Verification Status

### 6.1 Tier 1 Execution Summary (Foundation & Core Contracts)
- **Suite Target**: `tests/e2e/test_tier1_features.py`
- **Total Test Cases**: 30
- **Status**: Verified / Passing (30/30 passed)
- **Execution Command**: `& .\.venv\Scripts\python.exe -m pytest tests/e2e -v` (requires unsandboxed socket binding on Windows due to asyncio loopback socket creation).
- **Features Verified in Tier 1**:
  - Feature 1: Modular Monolith & Hexagonal Layering (Value object purity & domain exceptions)
  - Feature 3: UnitOfWork RLS Session Context (`SET LOCAL app.tenant_id = :id`, rollback, missing tenant isolation guard)
  - Feature 4: JWT Principal Authentication (Claims encoding, decoding, role extraction, token tamper rejection)
  - Feature 5: Generic Provider Registry (Thread-safe registration, normalization, instantiation, unknown provider error)
  - Feature 6: Automatic Fallback Chain (Primary provider execution, failover on exception, acceptance threshold predicate)
  - Feature 7: Event-Loop Bounded CPU Executor (`run_cpu_bound()` worker pool offload)
  - Feature 8 & 9: Swappable Chat Model Providers (OpenAI, Anthropic, OpenRouter capabilities and token pricing contracts)
  - Feature 10: Dense Embedding Providers Protocol (`EmbeddingProvider` protocol compliance, dimensions, async batch/query methods)
  - Feature 12: Structure-Aware Hybrid Chunking & Table Protection (Contiguous table row preservation)
  - Feature 17: Reciprocal Rank Fusion ($k=60$ deterministic rank score fusion)
  - Feature 19-23: Decision Layer First Contracts (Intent Router, Safety Guard, Chunk Relevance Grader, Grounding Judge schemas)
  - Feature 26: Mock SaaS Integration Client (All 5 endpoints: overview, subscription, invoices, billing email, helpdesk tickets)
  - Feature 31: Human Escalation Trigger (Threshold gating when confidence < 0.65 dispatches high-priority support ticket)
  - System Infrastructure: Healthz endpoints (`/healthz` for RagAssist and Mock SaaS) and auth token generation (`/v1/auth/token`).

### 6.2 Tier 2 Execution Summary (Pipeline & Workflow Integration)
- **Suite Target**: `tests/e2e/test_tier2_pipelines.py`
- **Total Test Cases**: 35
- **Status**: Verified / Passing (35/35 passed)
- **Execution Command**: `& .\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier2_pipelines.py -v`
- **Features Verified in Tier 2**:
  - Feature 11: Multi-Format Document Parsing (PDF table/page tagging, HTML script sanitization & heading hierarchy, Markdown AST blocks, PlainText UTF-8 preservation, Corrupt binary payload domain ParseError).
  - Feature 12: 5-Pass Structure-Aware Hybrid Chunking (AST pass, token bounds sentence splitting, sibling merging under same heading, section boundary preservation, table row preservation with repeated headers, and breadcrumb metadata propagation).
  - Feature 13: S3 Storage & SQS Ingestion Queue (Tenant prefix key scoping `tenants/{tenant_id}/documents/{document_id}/{filename}`).
  - Feature 14: Background Ingestion Worker (Worker idempotency on repeated SQS deliveries, atomic chunk replacement `replace_chunks`, vector dimension embedding contracts).
  - Feature 15: Dense Vector Search (pgvector cosine distance ranking with tenant boundary isolation).
  - Feature 16: Sparse Full-Text Search (PostgreSQL tsvector keyword search with boolean operators).
  - Feature 17: Reciprocal Rank Fusion ($k=60$ formula calculation, dense+sparse fusion dominance, rank deduplication).
  - Feature 18: Toggleable Reranker Cascade (Cross-Encoder GPU -> FlashRank CPU ONNX -> NoOp, candidate relevance grading threshold 0.50).
  - Feature 24: LangGraph State Machine Workflow (Cyclic execution path, query rewrite bounded loop <= 2, SaaS action tool routing skipping retrieval, input safety guard interception).
  - Feature 25: Persistent Conversation Checkpointer (Tenant-isolated thread namespace `{tenant_id}:{conversation_id}`, multi-turn state resumption).
  - Feature 27: Citation & Provenance Assembler (Title, page, section breadcrumbs, chunk ID fidelity).
  - Feature 31: Human Escalation Trigger (Grounding confidence < 0.65 triggering escalation).

### 6.3 Tier 3 Execution Summary (Multi-Tenant Boundary & Security Isolation)
- **Suite Target**: `tests/e2e/test_tier3_isolation.py`
- **Total Test Cases**: 58
- **Status**: Verified / Passing (58/58 passed)
- **Execution Command**: `& .\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier3_isolation.py -v`
- **Features Verified in Tier 3**:
  - Feature 2 & 3: Cross-Tenant Data Isolation & PostgreSQL Row-Level Security (RLS) (Vector store partition, retriever keyword boundary, transactional connection switching, tenant context isolation).
  - Feature 4: JWT Authentication, Signature Verification & Claim Integrity (Secret key verification, payload tampering rejection, algorithm "none" denial, expiration, mandatory claims, role spoofing rejection).
  - Feature 26: Role-Based Access Control (RBAC) & Tool Abuse Prevention (Approval policy for mutating actions, parameter schema enforcement, audit log Principal claim extraction and secret masking).
  - Feature 21: Prompt Injection, Guardrails & Fail-Closed Security (Zero-width character stripping, Cyrillic/Greek homoglyph normalization, DAN mode jailbreak detection, system prompt extraction, fail-closed decider crash handling).


