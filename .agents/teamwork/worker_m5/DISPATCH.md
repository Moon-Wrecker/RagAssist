# DISPATCH — worker_m5

- **Role**: Milestone 5 Implementer (Production Service, SSE Streaming API & Observability)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\worker_m5
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md

## Exclusive Write Ownership
You have exclusive write ownership over:
- `src/ragassist/container.py` (Dependency injection container wiring all modules & platform adapters)
- `src/ragassist/main.py` (FastAPI application factory, lifespan, middleware, routers)
- `src/ragassist/modules/assistant/api/router.py` (Conversation & message endpoints, SSE streaming)
- `src/ragassist/shared/observability/` (Prometheus metrics at `/metrics`, LangSmith tracing hook)
- `src/ragassist/cli/main.py` (Typer CLI commands)
- `tests/unit/test_api_sse.py`
- `tests/unit/test_cli.py`

DO NOT modify files outside your write ownership (e.g., `modules/knowledge/`, `modules/retrieval/`, `modules/actions/`).

## Task Instructions
1. Implement Dependency Injection Container in `src/ragassist/container.py`:
   - Initialize Database sessionmaker and UnitOfWork factory.
   - Initialize S3 storage client, SQS queue client.
   - Initialize LLM, Embedding, Decision, and Reranker fallback chains.
   - Wire Knowledge, Retrieval, Actions, Escalation, and Assistant services.
2. Implement FastAPI Application in `src/ragassist/main.py`:
   - Lifespan context manager: startup resource initialization, shutdown cleanup.
   - Security middleware: CORS, JWT Principal extraction dependency.
   - Error handlers: domain exceptions mapped to standard HTTP 4xx/5xx RFC 7807 problem details.
   - Healthcheck endpoints: `GET /health/live`, `GET /health/ready`.
   - Mount Prometheus metrics at `/metrics`.
   - Register routers: `/api/v1/auth`, `/api/v1/knowledge`, `/api/v1/conversations`.
3. Implement Conversation & Message Endpoints with SSE Streaming in `src/ragassist/modules/assistant/api/router.py`:
   - `POST /api/v1/conversations`: Create new conversation thread.
   - `GET /api/v1/conversations`: List tenant conversations.
   - `GET /api/v1/conversations/{id}`: Get conversation details.
   - `POST /api/v1/conversations/{id}/messages`: Send message and stream real-time SSE events.
   - SSE format strictly conforms to `docs/api/sse-contract.md`:
     - `event: token` with JSON `{text: "..."}`
     - `event: source` with JSON `{title: "...", page: 1, snippet: "..."}`
     - `event: action` with JSON `{tool: "...", status: "..."}`
     - `event: error` with JSON `{code: "...", message: "..."}`
     - `event: done` with JSON `{conversation_id: "...", message_id: "..."}`
4. Implement Prometheus Metrics in `src/ragassist/shared/observability/metrics.py`:
   - Request counts, latency histograms, LLM token counters, RAG retrieval scores.
5. Implement Typer CLI in `src/ragassist/cli/main.py`:
   - CLI commands: `ragassist serve`, `ragassist ingest <file>`, `ragassist chat`, `ragassist doctor`.
6. Write unit tests for API SSE streaming and CLI in `tests/unit/test_api_sse.py` and `tests/unit/test_cli.py`. Use `BypassSandbox=True` on Windows.
7. Write `changes.md` and `handoff.md` in `d:\Coding\RagAssist-1\.agents\teamwork\worker_m5\`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
