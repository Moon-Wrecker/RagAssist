# 2. Constraints

**Type:** Architecture · **Audience:** architects, engineers, reviewers · **Verified against:** `a989287`

**In plain English:** These are the rules that the design must follow. Some rules come from the project. Some come from the
tools that the project uses. Change a rule only with a new ADR.

## 2.1 Technical constraints

| Constraint | Detail | Source |
|---|---|---|
| Language and API | Python with FastAPI. All I/O is async. | `AGENTS.md`, `src/ragassist/main.py` |
| Database | PostgreSQL with the pgvector extension. One store for rows, vectors and keyword search. | [ADR 0001](../adr/0001-pgvector-unified-storage.md) |
| Tenant isolation | PostgreSQL row-level security ([RLS](../glossary.md)) is enabled and forced. The app role is not a superuser and has `NOBYPASSRLS`. | [ADR 0002](../adr/0002-row-level-security.md) |
| Agent framework | LangGraph with `AsyncPostgresSaver` for checkpoints. | `src/ragassist/runtime.py` |
| Queue and storage | AWS S3 and SQS. LocalStack replaces them in development. | `compose.yaml`, `infra/` |
| Event loop | The Windows ProactorEventLoop does not work with psycopg async. The runtime stops at start if it finds it. | `src/ragassist/runtime.py` |
| Embedding size | The `chunks.embedding` column is `vector(1536)`. Every embedding provider must return 1536 dimensions. | Migration `0001` |
| Web app | React, Vite, TanStack Query and Tailwind. nginx serves the built files. | [ADR 0009](../adr/0009-web-app.md), [ADR 0014](../adr/0014-web-delivery.md) |
| Containers | The web container runs as a non-root user. The port must be 1024 or higher. | [ADR 0014](../adr/0014-web-delivery.md) |

## 2.2 Architecture rules

The repository follows a modular monolith with hexagonal layers. The rules come from `AGENTS.md`.

| Rule | Meaning |
|---|---|
| Inward dependencies | `domain` imports nothing from `application`, `adapters` or `api`. `application` imports only `domain` and ports. |
| No frameworks in the core | `domain` and `application` do not import FastAPI, SQLAlchemy or an SDK. |
| Module isolation | A module calls another module only through a public `application` facade or an event. |
| Tenant from the token | `tenant_id`, `user_id` and `role` come only from the verified JWT `Principal`. They never come from model output or tool arguments. |
| Unit of work | Each database call on a tenant table runs inside a `UnitOfWork` that sets `app.tenant_id`. |
| Thread names | A LangGraph thread id has the form `{tenant_id}:{conversation_id}`. |
| Async I/O | All I/O is async. CPU-bound work runs in a bounded executor. |

The enforcement is in tests. `tests/hygiene/test_architecture.py` holds eight rules: domain-points-inward,
domain-no-frameworks, application-points-inward, application-no-frameworks, application-uses-platform-adapters,
module-isolation, kernel-independence and platform-below-modules. The `import-linter` contract in `pyproject.toml` holds
one rule only. It stops the domain layers from importing `ragassist.main` or `ragassist.container`.

## 2.3 Configuration and hygiene rules

| Rule | Meaning |
|---|---|
| No hardcoded values | No password, key, token, host, port or role name in code, tests, Docker files, CI or docs. |
| No defaults for deployment values | `Settings` has no default for such fields. A missing value stops the start. |
| Model choice by configuration | Models come from `config/models.yaml` and the environment, through `ProviderRegistry` and `FallbackChain`. |
| Decision layer first | Routing, safety, grading and grounding use the `Decider` port. |
| `.env.example` stays in sync | A change in `settings.py` changes `.env.example` in the same step. |
| Secret guards | Git hooks, CI and GitHub push protection block keys. See `AGENTS.md` section 3. |
| Documentation | An architecture change needs an ADR. An API change updates the OpenAPI file and the [SSE contract](../api/sse-contract.md). |
| Tests | Each feature or bugfix needs unit tests. Database, graph and security changes need more tests. See the [test guide](../testing.md). |

## 2.4 Conventions

| Convention | Detail |
|---|---|
| API version | Routers use the `/v1` prefix. `/healthz` and `/metrics` have no version. |
| Line endings | `.gitattributes` forces LF for shell scripts, Dockerfiles, SQL and Python. |
| Documentation style | ASD-STE100 style, Plain English, Diataxis, arc42, C4 and Mermaid. See `docs/contributing/writing-style.md`. |
| Commit messages | No AI attribution in commits, pull requests or contributor lists. |

## 2.5 Deviations from the rules

The code does not follow every rule yet. Section [11](11-risks-and-technical-debt.md) lists the gaps. The main gap is
that the PDF parser and the chunker run on the event loop and not in the bounded executor.
