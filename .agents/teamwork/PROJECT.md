# Project: Multi-Tenant RAG Assistant (RagAssist)
# Scope: Global Project Master Index

## Architecture

RagAssist is built as a **Modular Monolith** using **Hexagonal Architecture (Ports and Adapters)** with strict inward dependencies and defense-in-depth multi-tenant isolation.

```
                           ┌──────────────────────────────────────────────┐
                           │          External Clients / APIs             │
                           │  FastAPI (REST & SSE Streaming) / Typer CLI  │
                           └──────────────────────┬───────────────────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   Vertical Domain Modules                                        │
│  ┌───────────────────────┐   ┌───────────────────────┐   ┌────────────────────────────────────┐  │
│  │   modules/identity    │   │   modules/knowledge   │   │         modules/assistant          │  │
│  │  (Auth, Tokens, Deps) │   │  (Upload, Chunker)    │   │  (LangGraph Agent, State, Graph)   │  │
│  └───────────────────────┘   └───────────────────────┘   └─────────────────┬──────────────────┘  │
│  ┌───────────────────────┐   ┌───────────────────────┐                     │                     │
│  │   modules/retrieval   │   │    modules/actions    │◄────────────────────┤                     │
│  │  (Dense, Sparse, RRF) │   │  (Mock SaaS Tools)    │                     │                     │
│  └───────────────────────┘   └───────────────────────┘   ┌─────────────────▼──────────────────┐  │
│                                                          │        modules/escalation          │  │
│                                                          │      (HITL, Support Tickets)       │  │
│                                                          │                                    │  │
│                                                          └────────────────────────────────────┘  │
└─────────────────────────────────────────┬────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       Platform Layer                                             │
│  ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐   ┌─────────────────┐  │
│  │    platform/llm    │   │ platform/embeddings│   │ platform/decisions │   │ platform/rerank │  │
│  │ (OpenAI, Anthropic,│   │  (OpenAI, Local ST)│   │ (Router, Guard,    │   │ (Cross-Encoder, │  │
│  │  OpenRouter)       │   │                    │   │  Grader, Ground)   │   │  FlashRank ONNX)│  │
│  └────────────────────┘   └────────────────────┘   └────────────────────┘   └─────────────────┘  │
│  ┌────────────────────┐   ┌────────────────────┐                                                 │
│  │  platform/storage  │   │   platform/queue   │                                                 │
│  │    (S3 aioboto3)   │   │   (SQS aioboto3)   │                                                 │
│  └────────────────────┘   └────────────────────┘                                                 │
└─────────────────────────────────────────┬────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                        Shared Kernel                                             │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────┐  │
│  │    shared/domain    │  │    shared/security  │  │      shared/db      │  │shared/resilience│  │
│  │(TenantId, UserId)   │  │  (JWT, Principal)   │  │(UnitOfWork, RLS, UOW│  │ (Bounded Pool,   │  │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  │ FallbackChain)  │  │
│                                                                             └─────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Architectural Tenets
1. **Inward Dependency Rule**: Pure domain logic and protocols define interfaces. Adapters implement protocols. API controllers inject dependencies via Container.
2. **Tenant Isolation (Defense-in-Depth)**: `tenant_id` comes exclusively from verified JWT `Principal`. Every database operation runs inside `UnitOfWork` executing `SELECT set_config('app.tenant_id', :tid, true)`. LangGraph state threads are namespaced as `{tenant_id}:{conversation_id}`.
3. **Event Loop Safety**: All I/O is async. Heavy CPU/GPU inference (tokenization, ONNX, parsers, cross-encoders) is offloaded to `run_cpu_bound()`.
4. **Resilience & Fallbacks**: Models, embeddings, deciders, and rerankers utilize confidence-gated `FallbackChain` with graceful degradation (GPU -> CPU ONNX -> NoOp).

---

## Feature Inventory

Every feature discovered during the survey is cataloged and assigned to a specific milestone:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Modular Monolith & Hexagonal Layering | Strict inward dependencies (domain -> application -> adapters -> api) enforced by import-linter | M1 | AGENTS.md § 1 |
| 2 | Tenant Row-Level Security (RLS) | Database-level row isolation via PostgreSQL RLS on all tenant tables | M2 | AGENTS.md § 1.3, ADR 0002 |
| 3 | UnitOfWork RLS Session Context | Transactional context manager executing `SET LOCAL app.tenant_id = :id` | M1 | src/ragassist/shared/db/uow.py |
| 4 | JWT Principal Authentication | Token decoding/validation extracting `user_id`, `tenant_id`, and `role` claims | M1 | src/ragassist/shared/security/jwt.py |
| 5 | Generic Provider Registry | Thread-safe registry mapping provider names to factory functions | M1 | src/ragassist/shared/registry.py |
| 6 | Automatic Fallback Chain | Ordered execution of providers with acceptance criteria and automatic failover | M1 | src/ragassist/shared/resilience.py |
| 7 | Event-Loop Bounded CPU Executor | Offloads heavy CPU/GPU tasks to bounded thread pool | M1 | src/ragassist/shared/resilience.py |
| 8 | Swappable Chat Model Providers | Protocols & adapters for OpenAI, Anthropic, OpenRouter, and local OpenAI-compatible | M1 | src/ragassist/platform/llm/ |
| 9 | Model Capabilities & Token Pricing | Metadata inspection for models including tool support, context window, pricing | M1 | src/ragassist/platform/llm/ports.py |
| 10 | Dense Embedding Providers | Protocols & adapters for dense vector embeddings (OpenAI, SentenceTransformers) | M1 | settings.py, pyproject.toml |
| 11 | Multi-Format Document Parsing | PyMuPDF4LLM for PDFs (table/image structure preservation) and markdownify for HTML | M2 | ADR 0003, pyproject.toml |
| 12 | 5-Pass Structure-Aware Hybrid Chunking | Chonk AST parsing, token limits, sibling merging, table protection, header breadcrumbs | M2 | ADR 0003, settings.py |
| 13 | S3 Storage & SQS Ingestion Queue | Raw storage in S3 bucket `ragassist-docs` and async job dispatch via `ragassist-ingest` | M2 | compose.yaml, init.sh |
| 14 | Background Ingestion Worker | Async worker polling SQS, downloading from S3, chunking, embedding, inserting to pgvector | M2 | settings.py |
| 15 | Dense Vector Search with Iterative Scan | Cosine distance search over pgvector HNSW index using `relaxed_order` | M3 | ADR 0001, settings.py |
| 16 | Sparse Full-Text Search | PostgreSQL FTS tsvector search (`websearch_to_tsquery`) for exact keyword matches | M3 | ADR 0001, settings.py |
| 17 | Reciprocal Rank Fusion (RRF) | Fuses dense and sparse candidate rankings with constant k=60 | M3 | settings.py |
| 18 | Toggleable Reranker Chain | Local Cross-Encoder (GPU RTX 3060) -> FlashRank (CPU ONNX) -> None (RRF ordering) | M3 | ADR 0005, settings.py |
| 19 | Decision Layer First Architecture | System One decision models evaluating Choice/Score/Predicate with calibrated distributions | M1 | ADR 0004, settings.py |
| 20 | Query Intent Router | Classifies incoming message into `rag_search`, `saas_action`, `general_chat`, `human_escalation` | M1 | ADR 0004, settings.py |
| 21 | Input Safety & Prompt Injection Guard | Evaluates user input against prompt injection patterns and toxic payloads | M1 | AGENTS.md § 2.2, settings.py |
| 22 | Chunk Relevance Grader | Filters retrieved candidate chunks to eliminate noise and hallucinations | M1 | AGENTS.md § 2.2, ADR 0004 |
| 23 | Grounding & Hallucination Judge | Post-generation evaluator verifying answer statements against cited chunks | M1 | AGENTS.md § 2.2, settings.py |
| 24 | LangGraph State Machine Workflow | Cyclical graph orchestrating routing, retrieval, grading, rewriting, tools, synthesis | M4 | AGENTS.md § 1.3, pyproject.toml |
| 25 | Persistent Conversation Checkpointer | Saves and restores LangGraph execution state in PostgreSQL with tenant isolation | M4 | ADR 0001, AGENTS.md § 1.3 |
| 26 | Mock SaaS Integration Tools | Tools interacting with external SaaS: overview, subscription, invoices, billing email, ticket | M4 | services/mock_saas/main.py |
| 27 | Citation & Provenance Assembler | Attaches source document title, page numbers, and section breadcrumbs to answers | M4 | ADR 0003 |
| 28 | Conversation Lifecycle Endpoints | REST endpoints to create, list, and fetch conversation threads and messages | M5 | pyproject.toml, AGENTS.md |
| 29 | Server-Sent Events (SSE) Streaming | Real-time token streaming with structured lifecycle events (`token`, `source`, `done`) | M5 | docs/api/sse-contract.md |
| 30 | Document Ingestion Upload Endpoint | Multipart file upload endpoint streaming files to S3 and dispatching SQS ingest job | M2 | compose.yaml, settings.py |
| 31 | Human Escalation Trigger | Gated escalation when confidence or relevance < `ESCALATION_THRESHOLD` (0.65) | M4 | ADR 0004, services/mock_saas |
| 32 | Prometheus Metrics Instrumentation | Exposes standard HTTP and RAG application metrics at `/metrics` | M5 | pyproject.toml, settings.py |
| 33 | LangSmith Tracing Switch | Configurable distributed tracing of LangGraph chains and tool calls | M5 | settings.py, .env.example |
| 34 | RAG Triad Benchmark Runner | Automated evals assessing faithfulness, answer relevance, context precision | M5 | evals/, pyproject.toml |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Model & Decision Platform | Model catalog (`config/models.yaml`), LLM & Embedding provider registries, adapters, fallback chains, System One decision layer, routing, input guardrails, chunk relevance grader, grounding judge | Phase 0 Foundations | DONE (Gate 2 PASS: 783 unit tests, 66 adversarial tests, 30 Tier 1 E2E tests, clean forensic audit) |
| M2 | Ingestion & Knowledge Pipeline | Document parsers (PDF, HTML, MD), 5-pass Hybrid Chunker with table protection, S3/SQS adapters, pgvector document/chunk persistence models with RLS, background worker daemon, upload API | M1 | IN_PROGRESS (owned by milestone2_builder) |
| M3 | Hybrid Retrieval & Reranker Engine | pgvector dense cosine search (`relaxed_order`), PostgreSQL FTS sparse search, Reciprocal Rank Fusion ($k=60$), toggleable reranker chain (Cross-Encoder on RTX 3060 GPU -> FlashRank CPU ONNX -> none), retrieval service | M1, M2 | IN_PROGRESS (owned by milestone3_builder) |
| M4 | Agent Core, SaaS Actions & Escalation | Mock SaaS HTTP client & LangChain action tools, LangGraph state machine, PostgreSQL checkpointer (`{tenant_id}:{conversation_id}`), citation assembler, human escalation module | M1, M3 | IN_PROGRESS (owned by milestone4_builder) |
| M5 | Production Service, SSE & Observability | Dependency injection container, FastAPI conversation & message endpoints, SSE real-time streaming protocol, Prometheus metrics, Typer CLI, Arc42 complete documentation | M1, M2, M3, M4 | IN_PROGRESS (owned by milestone5_builder) |
| M6 | Final Milestone: Full E2E & Adversarial Pass | Phase 1: Pass 100% of E2E Test Suite (Tiers 1-4); Phase 2: Adversarial Coverage Hardening (Tier 5) with Challengers | M1-M5, E2E Test Suite | PLANNED |

### Parallel Track: E2E Testing Track
- **Orchestrator**: E2E Testing Orchestrator (`teamwork_orchestrator`)
- **Scope**: Build opaque-box, requirement-driven test infrastructure (`TEST_INFRA.md`) and comprehensive 4-tier test suite (~391 test cases across Tier 1, Tier 2, Tier 3, Tier 4). Publishes `TEST_READY.md`.
- **Status**: COMPLETE & VERIFIED. All 4 Tiers published in `TEST_READY.md` (163 tests: 30 Tier 1, 35 Tier 2, 58 Tier 3, 40 Tier 4; 162 passed, 1 xfailed, 0 failed, 100% pass rate). Ready for post-build verification of M2–M5.

### Parallel Track: Unit, Pending, Security & Gates Suites (test_writer_unit_suites)
- **Owner**: `.agents/teamwork/test_writer_unit_suites/` (conversation be9621e6)
- **Scope**: Acceptance suites for M2–M5 written before the code lands (knowledge, retrieval, rerank, LangGraph
  G1–G22, SSE, actions, escalation), the security tier (auth sweep, injection corpus, cross-tenant leak gate),
  integration on Postgres and LocalStack, hygiene and quality gates (coverage ratchet, flake check, pending and
  defect reports), and the interface appendix in `docs/testing.md`.
- **Status**: WRITTEN; runs against the builders' code as it lands. The live pieces (security, selfcheck,
  hygiene, M1 suites) run now. Modules not built yet report PENDING; see `reports/pending.md`.
- **For builders (M2–M5)**: the suites are the acceptance criteria. Do not edit `tests/`. Run
  `pytest -m pending -rs` to see what is missing. Interface changes are listed in
  `test_writer_unit_suites/handoff.md` ("Changes to the interface"). Open conflicts C-R1, C-R2, C-P1, C-P2,
  C-D1, C-D2, C-D3, C-S1 are in `test_writer_unit_suites/BRIEFING.md` and need a decision from the orchestrator.

---

## Interface Contracts

### 1. Model & Embedding Layer ↔ Consumer Modules
- **Protocols**: `ChatModelProvider`, `EmbeddingProvider` defined in `src/ragassist/platform/llm/ports.py`.
- **Method Signatures**:
  ```python
  class ChatModelProvider(Protocol):
      def get_chat_model(self, model: str, temperature: float = 0.0, max_tokens: int | None = None, streaming: bool = False) -> BaseChatModel: ...
      def get_capabilities(self, model: str) -> ModelCapabilities: ...
      def get_pricing(self, model: str) -> ModelPricing: ...

  class EmbeddingProvider(Protocol):
      async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
      async def embed_query(self, text: str) -> list[float]: ...
      def dimension(self) -> int: ...
  ```

### 2. Decision Layer ↔ Retrieval / Agent Core
- **Protocols**: `Decider` defined in `src/ragassist/platform/decisions/ports.py`.
- **DTOs & Methods**:
  ```python
  class RoutingDecision(BaseModel):
      route: Literal["rag_search", "saas_action", "general_chat", "human_escalation"]
      confidence: float
      reasoning: str

  class SafetyVerdict(BaseModel):
      is_safe: bool
      violation_categories: list[str] = []
      risk_score: float = 0.0

  class RelevanceScore(BaseModel):
      score: float # 0.0 to 1.0
      is_relevant: bool

  class GroundingVerdict(BaseModel):
      grounding_score: float # 0.0 to 1.0
      is_grounded: bool
      unsupported_claims: list[str] = []
  ```

### 3. Ingestion & Storage ↔ Retrieval Engine
- **Database Schema Contract**:
  - `documents` table: `id (UUID)`, `tenant_id (UUID)`, `title (VARCHAR)`, `s3_uri (VARCHAR)`, `created_at (TIMESTAMPTZ)`.
  - `document_chunks` table: `id (UUID)`, `document_id (UUID)`, `tenant_id (UUID)`, `chunk_index (INT)`, `content (TEXT)`, `embedding (vector(1536))`, `heading_path (TEXT)`, `page_number (INT)`, `metadata (JSONB)`.
  - RLS Policy on all tables: `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`.

### 4. Retrieval Engine ↔ Agent Core
- **Retrieval Result DTO**:
  ```python
  class RetrievedChunk(BaseModel):
      chunk_id: UUID
      document_id: UUID
      content: str
      score: float
      heading_path: str | None = None
      page_number: int | None = None
      metadata: dict[str, Any] = Field(default_factory=dict)

  class RetrievalService(Protocol):
      async def retrieve(self, tenant_id: TenantId, query: str, top_k: int = 6) -> list[RetrievedChunk]: ...
  ```

### 5. Mock SaaS Client ↔ Actions Module
- **Endpoints Contract**:
  - `GET /accounts/overview`: returns account details, plan, seat usage, balance.
  - `GET /accounts/subscription`: returns plan name, status, renewal date.
  - `GET /accounts/invoices`: returns invoice list (`inv_id`, `amount`, `status`).
  - `POST /accounts/billing-email`: updates billing email address (admin only).
  - `POST /helpdesk/tickets`: creates escalation support ticket with priority and description.

---

## Code Layout

```
src/ragassist/
├── main.py                          # FastAPI application factory
├── container.py                     # Dependency injection container
├── cli/
│   └── main.py                      # Typer CLI commands
├── worker/
│   └── ingestion_worker.py          # Background SQS ingestion worker
├── shared/
│   ├── domain/                      # Pure Python value objects & exceptions
│   ├── config/                      # Settings & pydantic configuration
│   ├── security/                    # JWT, Principal, FastAPI auth deps
│   ├── db/                          # SQLAlchemy Base, sessionmaker, UnitOfWork (RLS)
│   ├── resilience.py                # FallbackChain, run_cpu_bound thread pool
│   ├── registry.py                  # Generic ProviderRegistry
│   └── observability/               # Logging, Prometheus instrumentor, LangSmith
├── platform/
│   ├── llm/                         # ChatModelProvider protocol & adapters
│   ├── embeddings/                  # EmbeddingProvider protocol & adapters
│   ├── decisions/                   # Decider protocols & adapters
│   ├── rerank/                      # Reranker protocol & adapters
│   ├── storage/                     # S3 storage adapter
│   └── queue/                       # SQS queue adapter
└── modules/
    ├── identity/                    # User & Tenant identity management
    ├── knowledge/                   # Ingestion, parsers, hybrid chunker, persistence
    ├── retrieval/                   # Dense, sparse, RRF fusion, retrieval service
    ├── actions/                     # Mock SaaS client, LangChain action tools
    ├── escalation/                  # Human-in-the-loop escalation service
    └── assistant/                   # LangGraph agent, state, checkpointer, SSE API
```
