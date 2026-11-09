# Codebase Structure & Architecture Survey: RagAssist

**Date**: 2026-11-07  
**Author**: Codebase Structure Explorer (`explorer_survey_2`)  
**Scope**: Exploration of `src/ragassist/`, `tests/`, `config/`, `infra/`, `services/mock_saas/`, and `AGENTS.md`  

---

## 1. Executive Summary & Codebase Health

The **RagAssist** repository is architected as a **Modular Monolith** employing **Hexagonal Architecture (Ports & Adapters)** with strict inward dependencies and defense-in-depth tenant isolation.

### Current Status
- **Phase 0 (Foundations, Repo Hygiene, AGENTS.md, Docker Compose, Mock SaaS, RLS, Initial Tests)** is **verified complete**.
- Foundational domain value objects, security JWT/Principal handling, async PostgreSQL session management, transactional `UnitOfWork` with `SET LOCAL app.tenant_id`, bounded CPU execution threadpool, generic `FallbackChain`, and thread-safe `ProviderRegistry` are implemented and operational.
- All existing unit tests (`tests/unit/test_shared_kernel.py`) pass cleanly (3 passed in 0.28s).
- Configuration settings (`src/ragassist/shared/config/settings.py`) and environment template (`.env.example`) are 100% synchronized and comprehensively cover all phases (Phases 1 through 9).
- The repository structure provides designated skeleton packages for vertical modules (`actions`, `assistant`, `escalation`, `identity`, `knowledge`, `retrieval`) and horizontal platform adapters (`decisions`, `embeddings`, `llm`, `queue`, `rerank`, `storage`).

---

## 2. Exhaustive Codebase Inventory

### 2.1 Shared Kernel (`src/ragassist/shared/`)
The Shared Kernel provides cross-cutting foundational infrastructure without domain coupling:

| File Path | Type | Key Symbols / Classes | Purpose & Description |
|---|---|---|---|
| `shared/domain/__init__.py` | Domain | `TenantId`, `UserId`, `new_tenant_id()`, `new_user_id()`, `Entity`, `DomainError`, `EntityNotFoundError`, `TenantIsolationError`, `ValidationError` | Pure Python, immutable value types (`NewType` around UUID) and domain base exceptions. Zero external dependencies. |
| `shared/config/settings.py` | Config | `Settings(BaseSettings)`, `get_settings()` | Pydantic Settings v2 model reading `.env` with complete configuration attributes for application, DB/RLS, JWT, LocalStack, Mock SaaS, LLM providers, embeddings, retrieval/rerankers, chunking, deciders, observability, and ingestion workers. |
| `shared/security/jwt.py` | Security | `UserRole(Enum)`, `Principal`, `TokenPayload`, `create_access_token()`, `decode_access_token()` | JWT issuance and verification using HS256 and `SECRET_KEY`. Produces immutable `Principal` with `tenant_id`, `user_id`, `role`, `is_admin`, `is_agent`. |
| `shared/security/deps.py` | Security / API | `get_current_principal()`, `require_role(*roles)`, `get_tenant_uow()` | FastAPI HTTPBearer dependencies. Extracts JWT, enforces role authorization, and provides a scoped `UnitOfWork`. |
| `shared/db/models.py` | Persistence | `Base(DeclarativeBase)`, `TenantModel`, `UserModel` | SQLAlchemy async models for `tenants` and `users` tables with foreign keys and relationships. |
| `shared/db/session.py` | Persistence | `get_engine()`, `get_session_factory()`, `get_db_session()` | Async SQLAlchemy engine (`asyncpg`) and sessionmaker with connection pooling parameters (`DB_POOL_SIZE=20`, `DB_MAX_OVERFLOW=10`). |
| `shared/db/uow.py` | Persistence | `UnitOfWork`, `tenant_uow(tenant_id)` | Transaction manager that issues `SELECT set_config('app.tenant_id', :tid, true)` upon entry to enforce PostgreSQL Row-Level Security (RLS) on `app_user` connections. Scoped strictly to transaction lifetime (`is_local=true`). |
| `shared/resilience.py` | Resilience | `_BOUNDED_EXECUTOR`, `run_cpu_bound()`, `FallbackChain[T]` | Thread pool executor (4 workers) for offloading CPU-bound tasks from the asyncio event loop. Generic sequential `FallbackChain` with error logging and optional `is_acceptable` filter. |
| `shared/registry.py` | Platform | `ProviderRegistry[T]` | Generic thread-safe registry mapping string provider keys to factory functions with normalized lookups and error reporting. |
| `shared/observability/logging.py` | Observability | `configure_logging()` | Structlog setup supporting colored console rendering for development and JSON rendering for production, with timestamps and contextvars. |

---

### 2.2 Platform Layer (`src/ragassist/platform/`)
Abstract ports and concrete swappable infrastructure adapters:

| File Path | Component | Classes / Protocols | Status & Description |
|---|---|---|---|
| `platform/llm/ports.py` | LLM Port | `ModelPricing`, `ModelCapabilities`, `ChatModelProvider(Protocol)`, `EmbeddingProvider(Protocol)` | Protocol definitions for chat models and dense text embeddings. Declares methods for capabilities and LangChain model instantiation. |
| `platform/llm/adapters/openai_adapter.py` | LLM Adapter | `OpenAIAdapter(ChatModelProvider)` | Wraps `langchain_openai.ChatOpenAI` with pricing and capability declarations (tools, JSON schema, streaming, logprobs). |
| `platform/llm/adapters/anthropic_adapter.py` | LLM Adapter | `AnthropicAdapter(ChatModelProvider)` | Wraps `langchain_anthropic.ChatAnthropic` with pricing and capability declarations. |
| `platform/llm/adapters/openrouter_adapter.py` | LLM Adapter | `OpenRouterAdapter(ChatModelProvider)`, `OpenAICompatibleAdapter(ChatModelProvider)` | OpenRouter proxy adapter with custom headers (`HTTP-Referer`, `X-Title`) and local endpoint adapter for Ollama, vLLM, LM Studio. |
| `platform/decisions/` | Decision Port | *Pending Phase 2* | Directory structure exists. Needs `ports.py` and adapters for Jev, OpenAI Decisions, Strands Local, Semantic Router, and LLM structured fallbacks. |
| `platform/embeddings/` | Embeddings | *Pending Phase 1* | Directory structure exists. Needs concrete adapters for OpenAI, SentenceTransformers/HuggingFace, and FastEmbed. |
| `platform/rerank/` | Reranker Port | *Pending Phase 4* | Directory structure exists. Needs `Reranker` protocol and adapters for Cross-Encoder (`BAAI/bge-reranker-v2-m3`), FlashRank ONNX, and NoOp. |
| `platform/storage/` | Storage Port | *Pending Phase 3* | Directory structure exists. Needs S3 adapter via `aioboto3` for document ingestion and retrieval. |
| `platform/queue/` | Queue Port | *Pending Phase 3* | Directory structure exists. Needs SQS adapter via `aioboto3` for asynchronous document ingestion jobs and DLQ handling. |

---

### 2.3 Domain Modules (`src/ragassist/modules/`)
Vertical bounded contexts following Hexagonal Architecture:

| Module | Sub-packages | Status & Description |
|---|---|---|
| `modules/identity/` | `api/router.py`, `domain/`, `application/`, `adapters/` | Dev/test authentication router at `POST /v1/auth/token` issuing JWT tokens with `user_id`, `tenant_id`, `role`. Domain and application layers reserved for production tenant/user management. |
| `modules/knowledge/` | `domain/`, `application/`, `api/`, `adapters/chunkers/`, `adapters/parsers/`, `adapters/persistence/` | Package skeletons ready for Phase 3: document upload API, AST parsers (Markdown, PDF, HTML), 5-pass Hybrid Chunker, and pgvector document/chunk persistence models. |
| `modules/retrieval/` | `domain/`, `application/`, `adapters/` | Package skeletons ready for Phase 4: hybrid vector search (pgvector HNSW) + keyword search (Postgres FTS) + Reciprocal Rank Fusion (RRF). |
| `modules/assistant/` | `domain/`, `application/`, `api/`, `adapters/`, `graph/nodes/`, `prompts/` | Package skeletons ready for Phase 6 & 7: LangGraph multi-tenant state machine (`AssistantState`), graph nodes, conversation persistence (`PostgresSaver`), and SSE streaming API (`POST /v1/chat`). |
| `modules/actions/` | `tools/`, `adapters/`, `domain/` | Package skeletons ready for Phase 5: Mock SaaS HTTP client and LangChain tool definitions (`get_account_overview`, `get_subscription`, `list_invoices`, `update_billing_email`, `create_ticket`). |
| `modules/escalation/` | `domain/`, `application/` | Package skeletons ready for Phase 2 & 6: Human-in-the-loop escalation workflow, ticket tracking, and confidence gating. |

---

### 2.4 Worker, CLI, and API Entry Points
- `src/ragassist/main.py`: Application factory `create_app()` registering CORS middleware, `/healthz` health check, and `/v1/auth` routes.
- `src/ragassist/worker/`: Package reserved for `ingestion_worker.py` (SQS message polling and document processing pipeline).
- `src/ragassist/cli/`: Package reserved for Typer CLI commands (`worker start`, `db migrate`, `tenant create`).

---

### 2.5 External Services & Infrastructure (`services/`, `infra/`, `compose.yaml`)
- `services/mock_saas/main.py`: Standalone mock SaaS customer portal service running on FastAPI port 8001. Provides pre-seeded tenants:
  - Acme Corp (`a0000000-0000-0000-0000-000000000001`): Enterprise Scale plan, 50 seats (38 used), $2400/mo, active invoices `inv_acme_101`, `inv_acme_102`.
  - Globex Corp (`b0000000-0000-0000-0000-000000000002`): Pro Starter plan, 10 seats (9 used), $490/mo, active invoice `inv_globex_201`.
  - Endpoints: `GET /healthz`, `GET /accounts/overview`, `GET /accounts/subscription`, `GET /accounts/invoices`, `POST /accounts/billing-email`, `POST /helpdesk/tickets`.
- `infra/postgres/init.sql`: Enables `vector` and `uuid-ossp` extensions. Creates unprivileged role `app_user` with a password from the environment and grants database/schema permissions for RLS enforcement.
- `infra/localstack/init.sh`: Creates S3 bucket `ragassist-docs`, SQS dead-letter queue `ragassist-ingest-dlq`, and ingestion queue `ragassist-ingest` with redrive policy (`maxReceiveCount: 3`).
- `compose.yaml`: Multi-container topology for PostgreSQL 16 (`pgvector:pg16`), LocalStack 3.8.1 (s3, sqs, secretsmanager), mock SaaS (port 8001), and RagAssist API (port 8000).

---

## 3. Phase 0 Verification & Findings

### 3.1 Test Suite Execution
- **Existing Test File**: `tests/unit/test_shared_kernel.py`
  - Test 1: `test_domain_ids_and_exceptions` (Verifies strongly-typed UUID wrappers and domain hierarchy).
  - Test 2: `test_jwt_create_and_decode` (Verifies HS256 claims generation, expiration, role assignment, and extraction into `Principal`).
  - Test 3: `test_fallback_chain_success` (Verifies `FallbackChain` sequential recovery when primary member fails).
- **Test Result**: `3 passed in 0.28s` (Executed via `.venv\Scripts\pytest.exe tests/unit` with `PYTHONPATH=src`).

### 3.2 Technical Deep Dive: Windows Asyncio & Sandbox Port Binding
During test execution on Windows within the agent sandbox environment, a subtle runtime behavior was identified:
- `test_fallback_chain_success` is an async test utilizing `asyncio`.
- In Python 3.12 on Windows, the default event loop (`ProactorEventLoop`) creates an internal loopback socket pair (`socket.socketpair()`) bound to `127.0.0.1` for loop wakeups.
- In sandbox environments with restricted local loopback networking, `socket.socketpair()` blocks waiting for socket connection unless run in an environment permitting local loopback port binding (or using elevated permissions).
- **Takeaway for Phase 1-9 tests**: When running integration or async test suites, ensure tests mock external network I/O using `respx` or testcontainers, and run with appropriate local loopback access.

---

## 4. Hexagonal Architecture Compliance & Design Patterns

### 4.1 Inward Dependency Rule Verification
1. **Domain Layer**:
   - `src/ragassist/shared/domain/__init__.py` contains zero imports from outer layers (no FastAPI, no SQLAlchemy, no SDKs). Pure dataclasses and standard library `typing`, `uuid`, `datetime`. **100% Compliant.**
2. **Platform Layer**:
   - `src/ragassist/platform/llm/ports.py` defines abstract Protocols (`ChatModelProvider`, `EmbeddingProvider`).
   - Adapters (`openai_adapter.py`, `anthropic_adapter.py`, `openrouter_adapter.py`) import only from `ports.py` and `shared/config/settings.py`. **100% Compliant.**
3. **API Layer**:
   - `modules/identity/api/router.py` does not access database models directly; uses domain value types and security utilities. **100% Compliant.**

### 4.2 Multi-Tenant Isolation Pattern (Defense in Depth)
The established tenant isolation model implements three levels of defense:
1. **Identity Extraction**: The `Principal` is extracted exclusively from cryptographic verification of the caller's JWT in `shared/security/deps.py` via `get_current_principal()`. The `tenant_id` can never be spoofed by LLM prompts or request query parameters.
2. **Transactional RLS**: `UnitOfWork` (`shared/db/uow.py`) executes:
   ```sql
   SELECT set_config('app.tenant_id', :tid, true);
   ```
   Setting `is_local = true` binds the setting strictly to the current transaction. When connection pooling returns the session to the pool, the setting is cleanly rolled back, eliminating cross-tenant leakage.
3. **Database Engine Policies**: `app_user` is a non-superuser role subject to PostgreSQL Row-Level Security policies.

### 4.3 Async & Event Loop Protection
- Bounded thread pool executor (`_BOUNDED_EXECUTOR`, max 4 workers) in `shared/resilience.py`.
- Helper `run_cpu_bound()` ensures CPU-intensive tasks (tokenization, ONNX FlashRank reranking, PDF parsing) will not block the FastAPI async event loop.

---

## 5. Comprehensive Component Gap Analysis: Phases 1 through 9

The following matrix maps the required components across all remaining implementation phases against the current codebase:

| Phase | Required Component | Target File / Module | Status | What Needs to be Implemented |
|---|---|---|---|---|
| **Phase 1** | Model Catalog YAML | `config/models.yaml` | Missing | Model specifications (pricing, context window, capabilities, roles: generator, rewriter, agent, judge, decider). |
| **Phase 1** | Model Provider Registry | `src/ragassist/platform/llm/registry.py` | Missing | Factory integrating `config/models.yaml` with `ProviderRegistry[ChatModelProvider]`. |
| **Phase 1** | Embedding Provider Adapters | `src/ragassist/platform/embeddings/adapters/` | Skeleton | `OpenAIEmbeddingAdapter`, `OpenAICompatibleEmbeddingAdapter`, `SentenceTransformersEmbeddingAdapter`. |
| **Phase 1** | Embedding Fallback Chain | `src/ragassist/platform/embeddings/service.py` | Missing | Embeddings service orchestrating fallback chain. |
| **Phase 2** | Decision Ports & Models | `src/ragassist/platform/decisions/ports.py` | Missing | `Decider` protocol (`Choice`, `Score`, `Predicate`), DTOs (`RoutingDecision`, `RelevanceScore`, `GroundingScore`). |
| **Phase 2** | Decision Adapters | `src/ragassist/platform/decisions/adapters/` | Skeleton | `OpenAIDecisionsAdapter`, `JevAdapter`, `StrandsDeciderAdapter`, `SemanticRouterAdapter`, `LLMStructuredDeciderAdapter`. |
| **Phase 2** | Decision Fallback Chain | `src/ragassist/platform/decisions/service.py` | Missing | Confidence-gated fallback chain with `DECIDER_MIN_CONFIDENCE` (0.70). |
| **Phase 3** | S3 Storage Adapter | `src/ragassist/platform/storage/s3.py` | Missing | `aioboto3` S3 client for uploading and downloading raw documents. |
| **Phase 3** | SQS Queue Adapter | `src/ragassist/platform/queue/sqs.py` | Missing | `aioboto3` SQS client for enqueueing ingestion jobs and dead-letter queue redrive. |
| **Phase 3** | Document AST Parsers | `src/ragassist/modules/knowledge/adapters/parsers/` | Skeleton | `MarkdownParser`, `PDFParser` (`pymupdf4llm`), `HTMLParser` (`markdownify`), `PlainTextParser`. |
| **Phase 3** | 5-Pass Hybrid Chunker | `src/ragassist/modules/knowledge/adapters/chunkers/hybrid_chunker.py` | Skeleton | Structure AST pass, token limit pass, sibling merge pass, table protection pass, contextual header breadcrumb pass. |
| **Phase 3** | Knowledge Persistence & RLS | `src/ragassist/modules/knowledge/adapters/persistence/models.py` | Skeleton | `DocumentModel`, `DocumentChunkModel` with pgvector `Vector(1536)` and Alembic migrations. |
| **Phase 3** | Ingestion Worker Daemon | `src/ragassist/worker/ingestion_worker.py` | Skeleton | Async worker polling SQS, downloading from S3, running parser/chunker/embedder, persisting to DB. |
| **Phase 3** | Knowledge API | `src/ragassist/modules/knowledge/api/router.py` | Skeleton | Document upload, ingestion trigger, status querying, document deletion endpoints. |
| **Phase 4** | Vector Search Adapter | `src/ragassist/modules/retrieval/adapters/vector_search.py` | Skeleton | pgvector cosine similarity search with `iterative_scan = relaxed_order` and RLS. |
| **Phase 4** | Keyword Search Adapter | `src/ragassist/modules/retrieval/adapters/keyword_search.py` | Skeleton | PostgreSQL FTS `tsvector` / `ts_rank_cd` search. |
| **Phase 4** | Hybrid Search & RRF Fusion | `src/ragassist/modules/retrieval/application/fusion.py` | Missing | Reciprocal Rank Fusion ($k=60$) combining vector and keyword ranks. |
| **Phase 4** | Reranker Chain Adapters | `src/ragassist/platform/rerank/adapters/` | Skeleton | `CrossEncoderReranker` (GPU RTX 3060), `FlashRankReranker` (CPU ONNX), `NoOpReranker`. |
| **Phase 4** | Unified Retrieval Service | `src/ragassist/modules/retrieval/application/retrieval_service.py` | Missing | Query rewrite, parallel search, RRF fusion, reranking, chunk relevance grading. |
| **Phase 5** | Mock SaaS Client | `src/ragassist/modules/actions/adapters/saas_client.py` | Skeleton | Async HTTP client communicating with `services/mock_saas/` with JWT forwarding and retries. |
| **Phase 5** | SaaS Action Tools | `src/ragassist/modules/actions/tools/` | Skeleton | LangChain tools: `get_account_overview`, `get_subscription`, `list_invoices`, `update_billing_email`, `create_ticket`. |
| **Phase 5** | Tool Execution Authorization | `src/ragassist/modules/actions/application/tool_executor.py` | Missing | Role-based gatekeeper ensuring only `admin` can mutate data (e.g. billing email). |
| **Phase 6** | LangGraph State & Checkpoints | `src/ragassist/modules/assistant/graph/state.py` | Skeleton | `AssistantState` TypedDict, `PostgresSaver` with namespaced thread IDs (`{tenant_id}:{conversation_id}`). |
| **Phase 6** | LangGraph Nodes | `src/ragassist/modules/assistant/graph/nodes/` | Skeleton | `route_node`, `retrieve_node`, `tools_node`, `generate_node`, `grounding_node`, `escalate_node`. |
| **Phase 6** | LangGraph Workflow Compiler | `src/ragassist/modules/assistant/graph/builder.py` | Skeleton | StateGraph compilation with conditional edges for query rewriting, tool loops, and human escalation. |
| **Phase 7** | Dependency Injection Container | `src/ragassist/container.py` | Missing | Central container assembling providers, repositories, use cases, and graph workflows. |
| **Phase 7** | SSE Streaming Protocol | `src/ragassist/modules/assistant/api/sse.py` | Missing | Typed SSE event generator emitting `metadata`, `token`, `tool_call`, `tool_result`, `citations`, `escalation`, `done`. |
| **Phase 7** | Chat & Conversation Router | `src/ragassist/modules/assistant/api/router.py` | Skeleton | `POST /v1/chat`, `GET /v1/conversations`, `GET /v1/conversations/{id}/messages`. |
| **Phase 8** | Multi-Tenant Security Tests | `tests/security/` | Skeleton | Cross-tenant data leak tests, RLS bypass attempt tests, role enforcement tests, checkpoint hijack tests. |
| **Phase 8** | End-to-End Integration Tests | `tests/integration/` | Skeleton | Full ingestion pipeline test, RAG chat test, SaaS action tool test, human escalation test. |
| **Phase 9** | Typer CLI Application | `src/ragassist/cli/main.py` | Skeleton | CLI commands for ingestion, database migrations, tenant creation, and worker execution. |
| **Phase 9** | Prometheus Metrics & Tracing | `src/ragassist/shared/observability/` | Partial | Prometheus metrics middleware (`/metrics`), request latency counters, LangSmith trace decorators. |
| **Phase 9** | Arc42 Documentation & OpenAPI | `docs/arc42/`, `docs/api/` | Partial | Arc42 architecture chapters (1-12) and finalized SSE contract specification. |

---

## 6. Recommendations for Implementation Orchestration

1. **Phase 1 Priority**: Create `config/models.yaml` and implement the `ProviderRegistry` factory and embedding adapters (`OpenAIEmbeddingAdapter`, `SentenceTransformersEmbeddingAdapter`).
2. **Phase 2 Priority**: Build the Decision layer protocol and adapters before proceeding to graph nodes so that routing and chunk grading are ready.
3. **Database Migrations First**: Prior to Phase 3 and Phase 6, establish Alembic migrations for `documents`, `document_chunks`, `conversations`, and `messages` with explicit RLS policies and pgvector indices.
4. **Test Independence**: Utilize `respx` for mock HTTP calls (Mock SaaS, OpenAI, OpenRouter) and in-memory or SQLite/testcontainers for isolated unit and integration testing without requiring live Docker daemons during fast unit test runs.
