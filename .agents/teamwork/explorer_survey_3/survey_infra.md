# Infrastructure, Dependencies, and External Services Survey Report

**Explorer**: Infra and Dependencies Explorer (`explorer_survey_3`)  
**Timestamp**: 2026-11-07T20:20:00Z  
**Workspace**: `d:\Coding\RagAssist-1`  
**State Folder**: `d:\Coding\RagAssist-1\.agents\teamwork\explorer_survey_3`  

---

## Executive Summary

This survey provides an exhaustive audit of the runtime environment, dependencies, container infrastructure, local GPU capabilities, configuration management, and external integration boundaries across Phases 1 through 9 for the Multi-Tenant RAG Assistant project.

**Key Findings:**
1. **Python & Package Manager**: The project utilizes Python **3.12.10** inside `.venv`. The fast package manager `uv` (version 0.11.32) is installed locally at `C:\Users\ASUS\.local\bin\uv.exe` (currently not exported in the PowerShell PATH). No `uv.lock` file exists yet.
2. **Dependency State**: Foundational dependencies (FastAPI, Pydantic, SQLAlchemy 2, asyncpg, LangChain core, LangGraph, structlog, pyjwt) are installed in `.venv`. However, key ML and platform libraries specified in `pyproject.toml`—including `torch`, `sentence-transformers`, `rerankers[flashrank]`, `aioboto3`, `pgvector`, `alembic`, `chonkie`, `semantic-router`, `pymupdf4llm`, `markdownify`, and `typesafe-sdk`—are **not yet installed**.
3. **Container Infrastructure**: `compose.yaml` defines four services: `postgres` (`pgvector/pgvector:pg16` on port 5432), `localstack` (`localstack:3.8.1` on port 4566 for S3, SQS, Secrets Manager), `mock-saas` (custom FastAPI mock on port 8001), and `api` (port 8000). The Docker daemon was not reachable during inspection (`permission denied / npipe`), meaning local tests requiring live containers must rely on mocked adapters or starting Docker Desktop.
4. **Hardware & GPU Setup**: Host possesses an **NVIDIA GeForce RTX 3060 Laptop GPU** (Driver 610.74, CUDA 13.3, 6,144 MiB VRAM). PyTorch is not currently installed in `.venv`. The codebase is designed with dual-track execution: local Cross-Encoders on GPU when available, seamlessly falling back to CPU FlashRank (ONNX) and RRF order if PyTorch/CUDA is unavailable.
5. **Configuration Architecture**: `.env`, `.env.example`, and `src/ragassist/shared/config/settings.py` are strictly synchronized. The directory `config/` currently exists but is empty; `config/models.yaml` is scheduled to be created as part of Phase 1.

---

## 1. Runtime Environment, Dependencies, and Lockfile

### 1.1 Python Environment
- **Python Binary**: `d:\Coding\RagAssist-1\.venv\Scripts\python.exe`
- **Reported Version**: `Python 3.12.10` (64-bit Windows)
- **Specification in `pyproject.toml`**: `requires-python = ">=3.12,<3.13"` (Strict Python 3.12 constraint).

### 1.2 Package Manager (`uv`)
- **Binary Location**: `C:\Users\ASUS\.local\bin\uv.exe`
- **Reported Version**: `uv 0.11.32 (3010295ae 2026-07-23 x86_64-pc-windows-msvc)`
- **System PATH Observation**: Running bare `uv` failed with `CommandNotFoundException`. Workers executing `uv` commands should invoke `& C:\Users\ASUS\.local\bin\uv.exe` or prepend `$env:PATH = "C:\Users\ASUS\.local\bin;$env:PATH"`.
- **Lockfile Status**: No `uv.lock` exists in the repository root.

### 1.3 Dependency Audit (`pyproject.toml` vs Installed `.venv`)

| Dependency | Required Version (`pyproject.toml`) | Installed in `.venv` | Status | Purpose / Phase |
| :--- | :--- | :--- | :--- | :--- |
| `fastapi` | `>=0.115.0` | `0.162.2` | **Installed** | Core API framework (Phase 0, 8) |
| `uvicorn[standard]` | `>=0.31.0` | `0.54.0` | **Installed** | ASGI server |
| `pydantic` | `>=2.9.0` | `2.14.3` | **Installed** | Data validation & schemas |
| `pydantic-settings` | `>=2.5.0` | `2.16.2` | **Installed** | Settings management |
| `sqlalchemy[asyncio]` | `>=2.0.35` | `2.1.8` | **Installed** | Async ORM & Core (Phase 0, 3) |
| `asyncpg` | `>=0.29.0` | `0.32.0` | **Installed** | PostgreSQL async driver |
| `alembic` | `>=1.13.3` | None | **Missing** | Database migrations (Phase 3) |
| `pgvector` | `>=0.3.5` | None | **Missing** | Vector extension bindings (Phase 3) |
| `langgraph` | `>=0.2.34` | `1.2.20` | **Installed** | Orchestration graph (Phase 7) |
| `langgraph-checkpoint` | (sub-dep) | `4.3.1` | **Installed** | LangGraph checkpointer base |
| `langgraph-checkpoint-postgres`| `>=2.0.4` | None | **Missing** | Postgres conversation checkpointer (Phase 7) |
| `langchain` | `>=0.3.3` | `1.4.9` | **Installed** | LangChain abstractions |
| `langchain-core` | `>=0.3.10` | `1.7.6` | **Installed** | Core interfaces |
| `langchain-openai` | `>=0.2.2` | `1.7.4` | **Installed** | OpenAI chat & embedding adapter |
| `langchain-anthropic` | `>=0.2.3` | `1.7.10` | **Installed** | Anthropic Claude adapter |
| `langchain-openrouter` | `>=0.1.0` | None | **Missing** | OpenRouter integration (wrapped via OpenAIAdapter) |
| `chonkie` | `>=0.4.0` | None | **Missing** | Structure-aware chunking (Phase 2) |
| `rerankers[flashrank]` | `>=0.5.0` | None | **Missing** | Reranker chain & FlashRank ONNX (Phase 4) |
| `semantic-router` | `>=0.0.60` | None | **Missing** | Semantic route classification (Phase 5) |
| `pymupdf4llm` | `>=0.0.17` | None | **Missing** | Markdown-preserving PDF parser (Phase 2) |
| `markdownify` | `>=0.13.1` | None | **Missing** | HTML to Markdown conversion (Phase 2) |
| `aioboto3` | `>=13.2.0` | None | **Missing** | Async AWS S3 and SQS client (Phase 2) |
| `pyjwt[crypto]` | `>=2.9.0` | `2.15.1` | **Installed** | Tenant JWT authentication (Phase 0) |
| `structlog` | `>=24.4.0` | `26.1.0` | **Installed** | Structured JSON logging |
| `prometheus-fastapi-instrumentator`| `>=7.0.0` | None | **Missing** | Prometheus metrics endpoint (Phase 8) |
| `slowapi` | `>=0.1.9` | None | **Missing** | Rate limiting middleware (Phase 8) |
| `tenacity` | `>=9.0.0` | `9.2.1` | **Installed** | Retries & resilience |
| `httpx` | `>=0.27.2` | `0.28.1` | **Installed** | Async HTTP client (Mock SaaS, APIs) |
| `typesafe-sdk` | `>=0.1.0` | None | **Missing** | TypeSafe AI Jev Decider SDK (Phase 5) |
| `tiktoken` | `>=0.7.0` | `0.14.0` | **Installed** | Token counting & splitting |
| `poethepoet` | `>=0.29.0` | None | **Missing** | Task runner defined in pyproject.toml |
| `typer` | `>=0.12.5` | None | **Missing** | CLI tooling |
| `torch` (optional `ml`) | `>=2.4.0` | None | **Missing** | GPU Cross-Encoder inference (Phase 4) |
| `sentence-transformers` (`ml`)| `>=3.1.0` | None | **Missing** | Local CrossEncoder & Embeddings (Phase 1, 4) |
| `pytest` (`dev`) | `>=8.3.3` | `9.2.0` | **Installed** | Testing framework |
| `pytest-asyncio` (`dev`) | `>=0.24.0` | `1.4.1.post1` | **Installed** | Async test runner |
| `pytest-cov`, `testcontainers`, `respx`, `polyfactory`, `ruff`, `mypy`, `import-linter` | Various | None | **Missing** | Linter, typechecker, testcontainers |

---

## 2. Container Infrastructure & External Services

The project uses `compose.yaml` (at the root) for orchestrating local dependencies:

```yaml
# compose.yaml summary
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
  localstack:
    image: localstack/localstack:3.8.1
    ports: ["4566:4566"]
    environment:
      SERVICES: s3,sqs,secretsmanager
      AWS_DEFAULT_REGION: us-east-1
    volumes:
      - ./infra/localstack/init.sh:/etc/localstack/init/ready.d/init.sh:ro
  mock-saas:
    build:
      context: .
      dockerfile: infra/docker/mock_saas.Dockerfile
    ports: ["8001:8001"]
  api:
    build:
      context: .
      dockerfile: infra/docker/api.Dockerfile
    ports: ["8000:8000"]
```

### 2.1 PostgreSQL 16 + pgvector Service
- **Image**: `pgvector/pgvector:pg16`
- **Host Port**: `5432`
- **Superuser**: `postgres` / `postgres` (Connection string: `postgresql+asyncpg://postgres:<redacted>@localhost:5432/ragassist`)
- **Application Role**: `app_user` / `<redacted>` (Connection string: `postgresql+asyncpg://app_user:<redacted>@localhost:5432/ragassist`)
- **Initialization Script (`infra/postgres/init.sql`)**:
  - `CREATE EXTENSION IF NOT EXISTS vector;`
  - `CREATE EXTENSION IF NOT EXISTS "uuid-ossp";`
  - Creates role `app_user WITH LOGIN PASSWORD '<redacted>';`
  - Grants permissions on database `ragassist` and schema `public`.
  - Configures default privileges for new tables and sequences.
- **Tenant Isolation Enforcement**: Handled via PostgreSQL Row-Level Security (RLS) policies and `UnitOfWork` in `src/ragassist/shared/db/uow.py`. Every request sets `SET LOCAL app.tenant_id = :tenant_id`.

### 2.2 LocalStack AWS Emulation Service
- **Image**: `localstack/localstack:3.8.1`
- **Host Port**: `4566`
- **Services Enabled**: `s3`, `sqs`, `secretsmanager`
- **Region**: `us-east-1`
- **Initialization Script (`infra/localstack/init.sh`)**:
  - S3 Bucket: `s3://ragassist-docs`
  - SQS Queues:
    - Dead Letter Queue: `ragassist-ingest-dlq`
    - Main Queue: `ragassist-ingest` (Redrive policy: `maxReceiveCount=3`, deadLetterTargetArn pointing to `ragassist-ingest-dlq`).

### 2.3 Mock SaaS Integration Service
- **Source**: `services/mock_saas/main.py`
- **Host Port**: `8001`
- **Healthcheck**: `GET /healthz` -> `{"status": "ok"}`
- **Security**: Validates incoming `Authorization: Bearer <token>` and extracts `tenant_id` claim.
- **Pre-seeded Tenants**:
  1. **Acme Corp**: `a0000000-0000-0000-0000-000000000001`
     - Plan: "Enterprise Scale", 50 seats (38 used), $2400/mo, renews 2027-01-01
     - Invoices: `inv_acme_101` ($2400, paid), `inv_acme_102` ($2400, paid)
  2. **Globex Corp**: `b0000000-0000-0000-0000-000000000002`
     - Plan: "Pro Starter", 10 seats (9 used), $490/mo, renews 2026-12-15
     - Invoices: `inv_globex_201` ($490, paid)
- **API Endpoints**:
  - `GET /accounts/overview` -> `tenant_id`, `company_name`, `plan`, `status`, `billing_email`
  - `GET /accounts/subscription` -> `tenant_id`, `plan`, `seats`, `seats_used`, `monthly_spend`, `subscription_renews`
  - `GET /accounts/invoices` -> list of invoices
  - `POST /accounts/billing-email` -> updates billing email
  - `POST /helpdesk/tickets` -> creates helpdesk ticket (`id`, `subject`, `description`, `conversation_id`, `priority`, `status`, `created_at`)

### 2.4 Docker Daemon Runtime State
- Command `docker ps` returned permission denied / Docker engine pipe unavailable (`open C:\Users\ASUS\.docker\config.json: Access is denied / npipe:////./pipe/docker_engine`).
- **Implication**: Unit tests and local fakes can run without Docker, but running containers via `docker compose up -d` or integration tests with `testcontainers` requires Docker Desktop running with accessible pipes.

---

## 3. Configuration Management & Model Configuration

### 3.1 Settings Architecture
- **Settings Class**: `src/ragassist/shared/config/settings.py` (inherits `pydantic_settings.BaseSettings`).
- **Sync Status**: `.env` and `.env.example` are **100% synchronized** with all fields in `settings.py`.

### 3.2 Configuration Categories & Switches

| Category | Key Variables | Default / Current Values | Valid Options / Notes |
| :--- | :--- | :--- | :--- |
| **App & Env** | `APP_NAME`, `APP_ENV`, `DEBUG`, `LOG_LEVEL`, `API_V1_PREFIX`, `SECRET_KEY`, `CORS_ORIGINS` | `RagAssist`, `development`, `true`, `INFO`, `/v1` | `APP_ENV`: `development`, `test`, `staging`, `production` |
| **Database & RLS** | `DATABASE_URL`, `DATABASE_ADMIN_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT` | Ports to `localhost:5432`, pool size 20, overflow 10, timeout 30s | Non-admin uses `app_user`; migrations use `postgres` |
| **JWT & Security** | `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `DEV_AUTH_SECRET` | `HS256`, 1440 min (24h), `<redacted>` | Dev token issuer at `POST /v1/auth/token` |
| **AWS / LocalStack**| `AWS_REGION`, `USE_LOCALSTACK`, `LOCALSTACK_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_DOCS`, `SQS_QUEUE_INGEST`, `SQS_QUEUE_INGEST_DLQ` | `us-east-1`, `true`, `http://localhost:4566`, `test`, `test`, `ragassist-docs`, `ragassist-ingest`, `ragassist-ingest-dlq` | Set `USE_LOCALSTACK=false` in production for real AWS |
| **Mock SaaS** | `MOCK_SAAS_BASE_URL`, `MOCK_SAAS_TIMEOUT_SECONDS` | `http://localhost:8001`, `10.0`s | Points to mock SaaS container or test server |
| **LLM Providers** | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY` | Keys empty by default, compatible URL: `http://localhost:11434/v1` | Supports OpenAI, Anthropic, OpenRouter, and Ollama/vLLM |
| **LLM Roles** | `LLM_ROLE_GENERATOR_PRIMARY`, `LLM_ROLE_GENERATOR_FALLBACKS`, `LLM_ROLE_REWRITER_PRIMARY`, `LLM_ROLE_AGENT_PRIMARY`, `LLM_ROLE_JUDGE_PRIMARY`, `LLM_ROLE_DECIDER_FALLBACK` | Primary: `gen-default`, Fallback: `gen-openrouter-llama` | Role-based model abstraction |
| **Embeddings** | `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `EMBEDDING_BATCH_SIZE`, `VECTOR_SEARCH_TOP_K`, `VECTOR_SEARCH_ITERATIVE_SCAN` | `openai`, `text-embedding-3-small`, 1536, batch 64, top_k 30, `relaxed_order` | `iterative_scan`: `relaxed_order`, `strict_order` |
| **Keyword Search**| `KEYWORD_SEARCH_BACKEND`, `KEYWORD_SEARCH_TOP_K` | `fts`, 30 | `fts` (native Postgres), `paradedb` |
| **Hybrid Retrieval**| `RETRIEVAL_RRF_K`, `RETRIEVAL_TOP_N` | 60, 6 | RRF rank fusion formula: $RRF\_Score = \sum \frac{1}{K + rank}$ |
| **Reranker** | `RERANK_ENABLED`, `RERANKER_CHAIN`, `RERANK_CROSS_ENCODER_MODEL`, `RERANK_FLASHRANK_MODEL`, `RERANK_TIMEOUT_MS` | `true`, `cross_encoder,flashrank,none`, `BAAI/bge-reranker-v2-m3`, `ms-marco-TinyBERT-L-2-v2`, 1500ms | Dynamic GPU -> CPU ONNX -> RRF fallback |
| **Chunking** | `CHUNK_STRATEGY`, `CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS`, `CHUNK_MERGE_PEERS`, `CHUNK_SEMANTIC`, `CHUNK_PARENT_CHILD` | `hybrid`, 512, 64, `true`, `false`, `false` | 5-pass structure-aware hybrid chunking (ADR 0003) |
| **Decision Layer** | `DECIDER_CHAIN`, `ROUTER_DECIDER_CHAIN`, `DECIDER_MIN_CONFIDENCE`, `DECIDER_TIMEOUT_MS`, `ESCALATION_THRESHOLD`, `TYPESAFE_API_KEY`, `OPENAI_DECISIONS_API_KEY`, `STRANDS_DECIDER_ENDPOINT` | Decider chain: `openai_decisions,jev,llm_structured`, Router: `semantic_router,openai_decisions,llm_structured`, min conf 0.70, timeout 1000ms, esc threshold 0.65 | Fast System-One decision gating without text generation |
| **Observability** | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`, `PROMETHEUS_METRICS_ENABLED` | Tracing `false`, project `ragassist-dev`, prometheus `true` | LangSmith & Prometheus metrics |
| **Worker** | `WORKER_CONCURRENCY`, `WORKER_MAX_RETRIES`, `WORKER_VISIBILITY_TIMEOUT_SECONDS`, `WORKER_POLL_WAIT_SECONDS` | Concurrency 4, retries 3, visibility 120s, poll wait 10s | Background SQS ingestion worker |

### 3.3 Status of `config/models.yaml`
- The `config/` directory is currently empty.
- In accordance with `AGENTS.md` and `settings.py`, `config/models.yaml` must be created in Phase 1 to define:
  - Model definitions, alias mappings (`gen-default`, `gen-openrouter-llama`), provider bindings, token context sizes, capabilities (tools, JSON schema, streaming), and pricing per million tokens.

---

## 4. Hardware, GPU, Acceleration & Fallback Mechanisms

### 4.1 Host GPU Specifications
Direct inspection using `nvidia-smi` reveals:
- **GPU**: NVIDIA GeForce RTX 3060 Laptop GPU (Device 0)
- **Driver Version**: `610.74`
- **CUDA UMD Version**: `13.3`
- **Total VRAM**: `6,144 MiB` (~6 GB)
- **Current Memory Usage**: 0 MiB (idle)

### 4.2 Machine Learning Dependencies Status in `.venv`
- `torch`: **NOT installed**
- `sentence-transformers`: **NOT installed**
- `flashrank`: **NOT installed**
- `semantic-router`: **NOT installed**

### 4.3 Fallback Execution Strategy
The architecture incorporates multi-tier graceful degradation (ADR 0004 & ADR 0005):

1. **Reranker Layer**:
   ```
   [Retrieval Top-30 (Vector + FTS via RRF)]
                     │
                     ▼
       ┌───────────────────────────┐
       │ Cross-Encoder (GPU / Torch)│ ─── fails or timeout (>1500ms) ──┐
       │ BAAI/bge-reranker-v2-m3   │                                  │
       └───────────────────────────┘                                  │
                     │ (succeeds)                                     ▼
                     │                                 ┌───────────────────────────┐
                     │                                 │ FlashRank (CPU / ONNX)     │ ── fails ──┐
                     │                                 │ ms-marco-TinyBERT-L-2-v2  │            │
                     │                                 └───────────────────────────┘            │
                     │                                                │                         ▼
                     │                                                │           ┌───────────────────────────┐
                     │                                                │           │ None (Passthrough RRF)    │
                     │                                                │           │ Keep Original Top-N Order │
                     │                                                │           └───────────────────────────┘
                     ▼                                                ▼                         │
   [Final Top-6 Chunks Passed to Generation Graph] ◄────────────────────────────────────────────┘
   ```
2. **CPU-Bound Bounded Execution**:
   - `src/ragassist/shared/resilience.py` provides `run_cpu_bound(func, *args, **kwargs)` backed by `ThreadPoolExecutor(max_workers=4, thread_name_prefix="ragassist-cpu")`.
   - Prevents tokenization, ONNX inference, and document parsing from starving FastAPI's async event loop.
3. **Decision Layer Fallback**:
   - Router: `semantic_router` → `openai_decisions` → `llm_structured`.
   - Chunk Grading & Grounding: `openai_decisions` → `jev` → `llm_structured`.
   - If confidence is `< DECIDER_MIN_CONFIDENCE` (0.70) or an adapter fails/times out (`DECIDER_TIMEOUT_MS=1000`), the chain automatically advances to the next provider.

---

## 5. End-to-End External Integration Boundaries & Configuration Switches Across Phases 1 through 9

| Phase | Boundary / External Target | Protocols / Ports | Adapters & Ports Required | Key Configuration Switches |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 1: Model & Embedding Providers** | OpenAI, Anthropic, OpenRouter, Self-hosted Ollama/vLLM | HTTPS (443), HTTP (11434) | `ChatModelProvider` (ports.py), `EmbeddingProvider`, `FallbackChain`, `ProviderRegistry` | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` |
| **Phase 2: Ingestion, Chunking & Storage** | LocalStack S3 & SQS (or AWS in prod) | HTTP (4566), HTTPS (443) | `platform/storage` (S3), `platform/queue` (SQS), `modules/knowledge/adapters/chunkers` | `USE_LOCALSTACK`, `LOCALSTACK_ENDPOINT`, `S3_BUCKET_DOCS`, `SQS_QUEUE_INGEST`, `SQS_QUEUE_INGEST_DLQ`, `CHUNK_STRATEGY`, `CHUNK_MAX_TOKENS` |
| **Phase 3: Postgres + pgvector & Hybrid Retrieval** | PostgreSQL 16 + pgvector | TCP (5432) | `modules/retrieval/adapters/persistence`, `shared/db/session.py`, `shared/db/uow.py` | `DATABASE_URL`, `DATABASE_ADMIN_URL`, `VECTOR_SEARCH_TOP_K`, `VECTOR_SEARCH_ITERATIVE_SCAN`, `KEYWORD_SEARCH_BACKEND`, `RETRIEVAL_RRF_K` |
| **Phase 4: Reranker Chain** | Local GPU (RTX 3060 CUDA) or CPU (ONNX) | In-process C-extensions / ONNX Runtime | `platform/rerank/ports.py`, `CrossEncoderReranker`, `FlashRankReranker`, `NoOpReranker` | `RERANK_ENABLED`, `RERANKER_CHAIN`, `RERANK_CROSS_ENCODER_MODEL`, `RERANK_FLASHRANK_MODEL`, `RERANK_TIMEOUT_MS` |
| **Phase 5: Decision Layer** | OpenAI Decisions API, TypeSafe AI Jev, Strands Decider, SemanticRouter | HTTPS (443), HTTP (8002), in-process | `platform/decisions/ports.py`, `OpenAIDecisionsAdapter`, `JevAdapter`, `StrandsDeciderAdapter`, `SemanticRouterAdapter` | `DECIDER_CHAIN`, `ROUTER_DECIDER_CHAIN`, `DECIDER_MIN_CONFIDENCE`, `DECIDER_TIMEOUT_MS`, `TYPESAFE_API_KEY`, `OPENAI_DECISIONS_API_KEY` |
| **Phase 6: Mock SaaS Integration** | Mock SaaS Container / Service | HTTP (8001) | `modules/actions/tools/` (AccountOverviewTool, SubscriptionDetailsTool, InvoiceListTool, UpdateBillingEmailTool, CreateHelpdeskTicketTool) | `MOCK_SAAS_BASE_URL`, `MOCK_SAAS_TIMEOUT_SECONDS` |
| **Phase 7: LangGraph Assistant & Escalation** | Postgres Checkpointer, Mock SaaS Helpdesk | TCP (5432), HTTP (8001) | `modules/assistant/graph/`, `langgraph-checkpoint-postgres`, `modules/escalation/` | `ESCALATION_THRESHOLD`, `JWT_SECRET_KEY` |
| **Phase 8: SSE API, Rate Limiting & Metrics** | Client frontends, Prometheus Scraper, LangSmith Cloud | HTTP (8000), HTTPS (443) | `modules/assistant/api/`, `slowapi`, `prometheus-fastapi-instrumentator`, `shared/observability` | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `PROMETHEUS_METRICS_ENABLED`, `CORS_ORIGINS` |
| **Phase 9: Evaluation & Deployment** | Ragas / DeepEval, Terraform AWS / LocalStack | CLI / HTTPS | `evals/`, `infra/terraform/` | `APP_ENV=production`, `DEBUG=false` |

---

## 6. Recommendations & Actionable Guidance for Subsequent Phases

1. **uv Path Workaround**: Sub-agents running terminal commands should call `C:\Users\ASUS\.local\bin\uv.exe` directly, or configure `$env:PATH = "C:\Users\ASUS\.local\bin;$env:PATH"` in command scripts.
2. **Missing Dependencies Installation**:
   - To proceed with Phase 1 through Phase 9, workers should install missing packages from `pyproject.toml` using `uv pip install -e .` (and `uv pip install -e ".[ml,dev]"` if PyTorch/dev tools are needed).
   - If PyTorch on Windows CUDA is desired for RTX 3060: install torch with CUDA index (`uv pip install torch --index-url https://download.pytorch.org/whl/cu124` or `cu121`).
3. **Graceful CPU-Only Testing**:
   - Because the reranker and decision chains have full fallback support (`cross_encoder -> flashrank -> none` and `openai_decisions -> jev -> llm_structured`), workers can implement and test entire pipelines even before heavy CUDA weights are downloaded.
4. **Mocked Services for Unit Tests**:
   - Unit tests must use fakes and mocked HTTP clients (`respx`) to test Mock SaaS, LocalStack S3/SQS, and LLM providers without requiring running Docker daemon or external network connectivity.
