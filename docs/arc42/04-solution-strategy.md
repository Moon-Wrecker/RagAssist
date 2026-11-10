# 4. Solution strategy

**Type:** Architecture · **Audience:** architects, engineers, reviewers · **Verified against:** `a989287`

**In plain English:** This page lists the main ideas behind the design. Each idea answers one quality goal from
section [1](01-introduction-and-goals.md). Each row links to the ADR that holds the reason.

## 4.1 Strategy by quality goal

| Goal | Approach | Where | ADR |
|---|---|---|---|
| Tenant isolation | The database enforces isolation with forced RLS. Code adds a second layer: the principal comes only from the token. | `shared/db/uow.py`, `shared/db/scoped.py`, migration `0001` | [0002](../adr/0002-row-level-security.md) |
| Tenant isolation | A conversation belongs to one user. Other users get 404. Staff roles see the inbox. | `modules/assistant` | [0006](../adr/0006-conversation-access-and-approval-binding.md) |
| Grounded answers | A graph retrieves, grades and verifies. The assistant escalates when a check fails. | `modules/assistant/graph/` | [0004](../adr/0004-decision-layer.md) |
| Grounded answers | Hybrid retrieval joins vector and keyword search with rank fusion. A reranker orders the result. | `modules/retrieval`, `platform/rerank` | [0001](../adr/0001-pgvector-unified-storage.md), [0005](../adr/0005-reranker-chain.md) |
| Grounded answers | A 5-pass hybrid chunker keeps the structure of each document. | `modules/knowledge` | [0003](../adr/0003-hybrid-chunking.md) |
| Safe actions | A write tool stops the graph with `interrupt()`. The approval resumes the exact checkpointed call. Only an admin can approve. | `modules/assistant/graph/`, `modules/actions` | [0006](../adr/0006-conversation-access-and-approval-binding.md) |
| Resilience | Each model role has a chain of providers. Each decision has a chain of deciders. Rerankers and caches fall back or miss. | `config/models.yaml`, `platform/decisions`, `platform/rerank` | [0004](../adr/0004-decision-layer.md), [0005](../adr/0005-reranker-chain.md), [0013](../adr/0013-gemini-provider.md) |
| Resilience | A turn runs detached from the HTTP request. A closed tab does not cancel the turn. | `modules/assistant/application` | [0008](../adr/0008-live-events-handoff-and-detached-turns.md) |
| Operability | One compose file starts the stack. `ragassist init-env` writes a working `.env`. | `compose.yaml`, `src/ragassist/cli/` | [0014](../adr/0014-web-delivery.md) |
| Operability | Traces, metrics and JSON logs exist. | `shared/observability/` | [0012](../adr/0012-langfuse-tracing.md) |
| Speed | A cache layer covers embeddings, decisions and retrieval results. HTTP caching uses `ETag`. | `platform/cache`, `shared/http_cache.py` | [0015](../adr/0015-caching.md) |

## 4.2 Structural decisions

1. **Modular monolith.** One deployable API holds six modules: identity, knowledge, retrieval, assistant, actions and
   escalation. A separate worker process runs ingestion from the same code base.
2. **Hexagonal layers.** Each module has `domain`, `application`, `adapters` and `api` layers. A platform layer holds
   the adapters for models, embeddings, rerankers, cache, queue, storage and events.
3. **One database.** PostgreSQL holds rows, vectors, keyword indexes, checkpoints, events and sessions.
   This removes a second store to secure.
4. **Ports and fallbacks.** Each external service has a port. A registry builds a chain of adapters from configuration.
5. **Events through the database.** PostgreSQL `LISTEN` and `NOTIFY` carry small id-only events to all API processes.
   No separate broker is needed.
6. **Detached turns.** The assistant turn runs as a task that the API tracks. On shutdown the API waits for running
   turns to finish, up to 30 seconds.

## 4.3 Technology choices

| Area | Choice | Reason in one line |
|---|---|---|
| API | FastAPI | Async, typed, generates OpenAPI |
| Agent runtime | LangGraph | Checkpoints and `interrupt()` for approvals |
| Storage | PostgreSQL 16 with pgvector | One store with RLS |
| Index | HNSW (cosine) and GIN | Vector and keyword search in the same database |
| Password hashing | argon2id | Memory-hard hash. See [ADR 0007](../adr/0007-accounts-and-sessions.md). |
| Web | React, Vite, TanStack Query, Tailwind | See [ADR 0009](../adr/0009-web-app.md). |
| Web delivery | nginx-unprivileged | Non-root, one origin. See [ADR 0014](../adr/0014-web-delivery.md). |
| Tracing | Langfuse, optional LangSmith | See [ADR 0012](../adr/0012-langfuse-tracing.md). |

## 4.4 Organisational decisions

- Each change follows Goal, Research, Implement. The module docstring or the ADR records the sources.
- A test gate guards each change. The [test guide](../testing.md) describes the tiers.
- Several layers keep secrets out of the repository: git hooks, CI scans and GitHub push protection.
