# AGENTS.md — Repository Rules, Architecture & Hygiene

This file defines the mandatory rules for both human engineers and AI coding assistants working in **RagAssist**.

## 1. Architecture & Layering Rules (Hexagonal + Modular Monolith)

The repository uses a **Modular Monolith** organized into **vertical bounded contexts** (`src/ragassist/modules/*`), backed by a **Platform** layer (`src/ragassist/platform/*`) for swappable AI/infra adapters and a **Shared Kernel** (`src/ragassist/shared/*`).

1. **Inward Dependency Rule (enforced by `import-linter`):**
   - `domain/` is pure Python + Pydantic value objects. It MUST NOT import from `application/`, `adapters/`, `api/`, FastAPI, SQLAlchemy, or external SDKs.
   - `application/` (use cases) imports only from `domain/` and abstract `ports` (`Protocol`).
   - `adapters/` (persistence, parsers, chunkers, SDK clients) implements `domain/` or `platform/` ports.
   - `api/` (FastAPI routers, HTTP DTO schemas, SSE) calls `application/` use cases via dependency injection (`container.py`).
2. **Module Isolation:**
   - Modules communicate through public `application` facades or domain events—never by reaching into another module's `adapters/persistence` models directly.
3. **Tenant Isolation (Defense in Depth):**
   - `tenant_id`, `user_id`, and `role` come **exclusively** from the verified JWT `Principal` (`shared/security`), never from LLM outputs or tool arguments.
   - Every database operation on tenant-scoped tables MUST run inside `UnitOfWork` (`shared/db/uow.py`), which opens an explicit transaction and executes `SET LOCAL app.tenant_id = :tenant_id` so PostgreSQL Row-Level Security (RLS) enforces isolation.
   - LangGraph `thread_id` values MUST be namespaced as `{tenant_id}:{conversation_id}` and verified against the `conversations` table before checkpoint access.
4. **Async & Event-Loop Safety:**
   - All I/O (Postgres, S3, SQS, HTTP, LLM calls) MUST be async.
   - All CPU-bound work (PDF layout parsing, tokenization, FlashRank ONNX, local Cross-Encoder / GPU inference) MUST run in `asyncio.to_thread()` via the bounded executor in `shared/resilience.py`.

## 2. Configuration & Provider Abstraction Rules

1. **No Hardcoded Models or Keys:**
   - All LLM, Embedding, Decider, and Reranker choices go through `ProviderRegistry` + `FallbackChain` configured via `config/models.yaml` and environment variables.
2. **Decision Layer First:**
   - Routing, input safety guards, chunk relevance grading, and grounding checks use the `Decider` port (`jev`, `openai_decisions`, `strands_local`, `semantic_router`, `llm_structured`, `rules`) with confidence-gated fallback chains.
3. **Toggleable Reranker Chain:**
   - Reranking uses the `Reranker` port (`cross_encoder`, `flashrank`, `api`, `decision`, `noop`). On machines with a GPU (e.g. RTX 3060), `cross_encoder,flashrank,none` is the default chain; if `torch`/CUDA or weights are unavailable, it falls back automatically to `flashrank` then `none`.

## 3. Repository Hygiene Rules (Always On)

Every commit or change MUST keep the repository hygiene files synchronized:

1. **`.env.example` Synchronization:**
   - Whenever you add, rename, or remove a field in `src/ragassist/shared/config/settings.py`, you MUST update `.env.example` in the same step with comments, safe defaults, and empty placeholders for secrets.
2. **`.gitignore` and `.dockerignore` Synchronization:**
   - Whenever you introduce a new tool, cache directory, local weight folder, build output, or artifact path, update both `.gitignore` and `.dockerignore`.
3. **Line Endings & Formatting:**
   - `.gitattributes` enforces `eol=lf` on shell scripts, Dockerfiles, SQL, and Python files so Docker containers on Windows (WSL2) never fail on CRLF shebangs.
4. **Documentation & ADRs:**
   - Architectural changes require adding or updating an ADR in `docs/adr/` and keeping `docs/arc42/` aligned.
   - API changes require keeping OpenAPI schemas and `docs/api/sse-contract.md` up to date.
5. **Research Before Implementation (Goal → Research → Implement):**
   - Before writing any component, state its goal in one or two sentences.
   - Then research it: read the official documentation of every library, API or concept involved (LangGraph, LangChain, pgvector, FastAPI, SQLAlchemy, aioboto3, `rerankers`, `chonkie`, `pymupdf4llm`, Jev, OpenAI Decisions, etc.), plus reputable blogs and existing open-source solutions.
   - Prefer adopting or adapting a proven solution over writing your own. Write custom code only for domain logic that no library covers.
   - Record what you consulted (doc URL or repo, and the decision it led to) in the module docstring, the PR description, or the relevant ADR in `docs/adr/`.
   - Never guess an SDK signature. If the docs cannot be reached, say so and mark the code as unverified.
6. **Testing Gate:**
   - Every new feature or bugfix requires unit tests (`tests/unit/`) and, where database/RLS or graph flows are touched, integration (`tests/integration/`), graph (`tests/graph/`), or security (`tests/security/`) tests.
7. **No Hardcoded Credentials or Deployment Values (Hard Rule, Always On):**
   - No password, key, token, secret, connection string with credentials, or deployment-specific value (host, port, role name, endpoint) may appear in code, tests, Docker/Compose files, CI workflows, docs or git history. Not even as a "development default".
   - `src/ragassist/shared/config/settings.py` defines **no defaults** for such values: a field without a default is required, and the value lives in `.env` (never committed). `.env.example` is the template: secrets are blank, everything else is a safe non-secret value. `ragassist init-env` generates a working `.env` with random secrets.
   - The only permitted code defaults are an empty string for optional third-party API keys and overrides.
   - Tests and CI generate their own throwaway secrets at run time (`secrets.token_urlsafe`); they never embed key-shaped literals either.
   - Before committing, grep the diff for `password`, `secret`, `token`, `api_key` literals. If a secret was ever committed, treat it as leaked: rotate it and purge it from history.
8. **Secret Guards (Hard Rule, Always On):** a key must never reach the remote. Four layers enforce it; do not bypass any of them.
   - **Git hooks** (`.githooks/pre-commit`, `.githooks/pre-push`, both run `scripts/check_secrets.py`). Enable once per clone with `git config core.hooksPath .githooks`. Never use `--no-verify`.
   - **CI** runs the same scanner over the whole tree and over every commit of a pull request (blocking); a hygiene test does the same in the unit run.
   - **GitHub push protection and secret scanning** are enabled on the repository and reject known provider keys server-side.
   - **Where real values live:** only the git-ignored `.env` (or the deployment's secret store). A value a user pastes into a chat goes into `.env` and nowhere else: not into code, tests, docs, fixtures, commit messages, PR text or logs.
   - A hook is a seatbelt, not a vault: a key that was ever pushed is leaked. Rotate it first, then purge it. A line may carry `secret-scan: allow` only for a documented non-secret value.
