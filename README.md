# RagAssist

A production-ready multi-tenant retrieval-augmented support assistant built as a **Hexagonal Modular Monolith** on **FastAPI**, **LangGraph**, and **PostgreSQL 16 + pgvector**.

---

## Architecture Highlights

- **Bounded Contexts (`src/ragassist/modules/*`)**:
  - `identity` — JWT authentication, tenant principal validation, and dev/local token generation (`POST /v1/auth/token`).
  - `knowledge` — Document ingestion pipeline (`POST /v1/documents`), S3 storage, SQS async dispatch, structure-aware parsing (`PyMuPDF4LLM`, Markdown, HTML, CSV, JSON), recursive token chunking (`Chonkie`), contextual headers, and batch embeddings (`text-embedding-3-small`, `768` dimensions via Matryoshka).
  - `retrieval` — Hybrid retrieval combining `pgvector` HNSW cosine similarity and PostgreSQL Full-Text Search (`tsvector`/`GIN`), fused via Reciprocal Rank Fusion ($k = 60$) and refined by a toggleable reranker chain (`cross_encoder` -> `flashrank` -> `none`).
  - `assistant` — 11-node cyclic **LangGraph** workflow (`security_guard_node`, `intent_router_node`, `query_rewriter_node`, `hybrid_retrieve_node`, `rerank_node`, `grade_documents_node`, `tool_executor_node`, `generate_answer_node`, `hallucination_check_node`, `escalate_node`, `audit_and_respond_node`) with PostgreSQL checkpointing (`AsyncPostgresSaver`) and real-time Server-Sent Events (SSE) streaming.
  - `actions` — Sandboxed SaaS account tools (`get_account_status`, `list_recent_invoices`, `update_billing_email`, `create_support_ticket`) backed by circuit breakers, exponential backoff, and strict RBAC enforcement.
  - `escalation` — Human-in-the-loop (HITL) escalation tickets (`GET /v1/escalations`, `POST /v1/escalations/{id}/resolve`) resuming suspended LangGraph threads.
- **Platform Layer (`src/ragassist/platform/*`)**:
  - Swappable **LLM** (`OpenAI`, `Anthropic`, `Gemini`, `OpenRouter`, any OpenAI-compatible server such as `Ollama`), **Embedding**, **Reranker**, and **System One Decision Layer** (`Jev`, `OpenAI Decisions`, `Strands Local`, `Semantic Router`, `LLM Structured`, `Rules`) adapters configured via [`config/models.yaml`](config/models.yaml) with automatic fallback chains.
  - **LLM providers** (set the key in `.env`; see [ADR 0013](docs/adr/0013-gemini-provider.md)):

    | Provider (`config/models.yaml`) | Settings | Example models |
    | --- | --- | --- |
    | `openai` | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini` |
    | `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet`, `claude-3-5-haiku` |
    | `gemini` | `GEMINI_API_KEY`, `GEMINI_BASE_URL` | `gemini-flash-latest`, `gemini-flash-lite-latest`, `gemini-pro-latest` |
    | `openrouter` | `OPENROUTER_API_KEY` | `openrouter-llama-3.1-70b` |
    | `openai_compatible` | `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_MODEL` | local Ollama / vLLM |

    Gemini is a fallback in every role chain and is skipped while `GEMINI_API_KEY` is empty. To use it first, set e.g.
    `LLM_ROLE_GENERATOR_PRIMARY=gemini-flash`. `OPENAI_COMPATIBLE_*` stays reserved for a local server.
- **Defense-in-Depth Multi-Tenancy**:
  - `tenant_id`, `user_id`, and `role` are extracted exclusively from verified JWT principals (`src/ragassist/shared/security/jwt.py`).
  - Every tenant-scoped database operation executes inside [`UnitOfWork`](src/ragassist/shared/db/uow.py), which opens a transaction and runs `SET LOCAL app.tenant_id = :tenant_id` enforced by PostgreSQL `ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
  - LangGraph `thread_id` checkpoints are strictly namespaced as `{tenant_id}:{conversation_id}`.
- **Zero Hardcoded Credentials Policy**:
  - [`src/ragassist/shared/config/settings.py`](src/ragassist/shared/config/settings.py) contains zero default secrets, passwords, or connection strings. All runtime configuration is loaded from `.env` (generated via `ragassist init-env` from `.env.example`).

---

## Quick Start & Deployment Guide

### 1. Environment Setup

```bash
# Create virtual environment and install dependencies
uv venv && uv pip install -e ".[dev]"

# Generate a local .env with cryptographically random secrets from .env.example
ragassist init-env
```

Turn on the secret guard once per clone. It refuses any commit or push that contains a key, token or password
(`scripts/check_secrets.py`; CI runs the same scan, and GitHub push protection is enabled on the repository):

```bash
git config core.hooksPath .githooks
```

Real keys live only in the git-ignored `.env`.

### 2. Start Local Infrastructure (Docker Compose)

```bash
# Starts PostgreSQL 16 (pgvector), LocalStack (S3 + SQS), and Mock SaaS API
docker compose up -d postgres localstack mock-saas
```

### 3. Run Database Migrations & Seed Demo Data

```bash
# Apply Alembic migrations (creates schema, HNSW/GIN indexes, and RLS policies)
ragassist db upgrade

# Seed demo tenants and users; prints a one-time set-password link per demo account
ragassist seed

# Or create your own workspace; prints the first administrator's one-time link
ragassist workspace create --name "Acme Inc" --slug acme-inc --admin-email you@example.com
```

Open a link (`<WEB_BASE_URL>/accept#token=...`, or `POST /v1/auth/invites/accept` with the token) to set a password.
People sign in with workspace slug, email and password; administrators add more people from the team API. See
[ADR 0007](docs/adr/0007-accounts-and-sessions.md).

### 4. Run the API Server & Ingestion Worker

```bash
# Terminal 1: Start FastAPI server (or uvicorn ragassist.main:create_app --factory --reload)
ragassist serve --reload

# Terminal 2: Start async SQS document ingestion worker
ragassist worker
```

---

## Core API Endpoints

| Method & Path | Description | Auth |
|---|---|---|
| `GET /healthz`, `GET /readyz` | Liveness and readiness probes | Public |
| `GET /metrics` | Prometheus metrics endpoint | Bearer JWT (admin) |
| `POST /v1/auth/token` | Issue development JWT (`development`/`test` only; needs the `X-Dev-Auth-Secret` header) | Dev secret |
| `POST /v1/auth/login` | Sign in with workspace, email and password; sets the refresh cookie | Public |
| `POST /v1/auth/refresh`, `POST /v1/auth/logout` | Rotate or end the session (refresh cookie + `Origin`) | Cookie |
| `GET /v1/auth/me` | The signed-in user and workspace | Bearer JWT |
| `POST /v1/auth/invites/accept` | Spend an invite or reset link: set a password and sign in | Public (token) |
| `/v1/team/members`, `/v1/team/invites` | List and manage members, roles, invitations, reset links | Bearer JWT (admin) |
| `POST /v1/documents` | Upload document (`PDF`, `MD`, `HTML`, `CSV`, `JSON`, `TXT`) for async ingestion | Bearer JWT |
| `GET /v1/documents` | List tenant documents and ingestion status | Bearer JWT |
| `GET /v1/documents/{id}` | Retrieve specific tenant document metadata | Bearer JWT |
| `DELETE /v1/documents/{id}` | Delete tenant document and vectors | Bearer JWT |
| `POST /v1/conversations` | Create a new conversation thread | Bearer JWT |
| `GET /v1/conversations` | List tenant conversations | Bearer JWT |
| `POST /v1/conversations/{id}/messages` | Send a user message and stream SSE events (`status`, `token`, `tool_call`, `citation`, `escalation`, `done`) | Bearer JWT |
| `GET /v1/escalations` | List pending human-in-the-loop escalations for tenant | Bearer JWT |
| `POST /v1/escalations/{id}/resolve` | Submit human agent resolution and resume LangGraph thread | Bearer JWT |

See [`docs/api/sse-contract.md`](docs/api/sse-contract.md) for the complete Server-Sent Events streaming specification.

---

## Testing & Evaluation Suite

### Automated Test Tiers

```bash
# Fast hermetic suites (unit, LangGraph state machine, security, hygiene, E2E)
pytest tests/unit tests/graph tests/security tests/hygiene tests/e2e

# Real PostgreSQL 16 + pgvector + RLS integration suite
pytest tests/integration

# Architectural boundary enforcement (Hexagonal inward dependency contracts)
lint-imports
```

See [`docs/testing.md`](docs/testing.md) for full details on test tiers, markers, and coverage gates.

### Golden Dataset Evaluation Harness

Run the automated RAG & Agent evaluation benchmark (`Hit@5`, `MRR@5`, `nDCG@5`, `Faithfulness`, `Answer Relevance`, `Citation Precision/Recall`, `Prompt Injection Defense`, and `Escalation Accuracy`):

```bash
python -m evals.runner --offline
```

Reports are written to [`evals/reports/eval_summary.md`](evals/reports/eval_summary.md) and [`evals/reports/eval_summary.json`](evals/reports/eval_summary.json).

---

## Documentation & Architecture Decision Records

- **Repository Rules & Hygiene**: [`AGENTS.md`](AGENTS.md)
- **Architecture Decision Records**: [`docs/adr/`](docs/adr/) (`ADR-0001` through `ADR-0008`)
- **SSE Streaming Contract**: [`docs/api/sse-contract.md`](docs/api/sse-contract.md)
- **Testing Strategy**: [`docs/testing.md`](docs/testing.md)
- **CI/CD Pipeline**: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (enforces `ruff`, `mypy`, `lint-imports`, unit/graph/security/hygiene tests, PostgreSQL integration tests, and coverage gates on every pull request).
