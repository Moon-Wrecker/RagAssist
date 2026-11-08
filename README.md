# RagAssist

A multi-tenant retrieval-augmented support assistant, built as a **modular monolith** (hexagonal architecture)
on FastAPI, LangGraph and PostgreSQL + pgvector.

* **Bounded contexts** live in `src/ragassist/modules/*` (knowledge, retrieval, assistant, actions, escalation),
  on top of a swappable AI/infra **platform** layer and a small **shared kernel**.
* **Tenant isolation is defence in depth**: identity comes only from the verified JWT principal, every tenant-scoped
  query runs inside a `UnitOfWork` that sets `app.tenant_id` for PostgreSQL row-level security, and LangGraph threads
  are namespaced per tenant.
* **Providers are configuration**: LLM, embedding, decision and reranker choices go through the provider registry and
  fallback chains defined in `config/models.yaml`.

The rules every contributor (human or AI) follows are in [AGENTS.md](AGENTS.md); architecture notes are in `docs/`
(ADRs in `docs/adr/`, the testing strategy in `docs/testing.md`, the streaming contract in `docs/api/sse-contract.md`).

## Quick start

```bash
uv venv && uv pip install -e ".[dev]"
cp .env.example .env            # fill in the secrets you need; every key is documented
docker compose up -d postgres localstack   # PostgreSQL + pgvector, LocalStack (S3/SQS)
uvicorn ragassist.main:create_app --factory --reload
```

## Tests

```bash
pytest tests/unit tests/graph tests/security tests/hygiene   # fast tiers, no Docker
pytest tests/integration                                     # real PostgreSQL (testcontainers or TEST_DATABASE_ADMIN_URL)
```

Tests are contract-first and scenario-by-scenario. Suites for modules that are not built yet **skip with a
`PENDING:` reason** until the code lands, and known implementation defects are tracked as strict expected
failures (`reports/defects.md`). See [docs/testing.md](docs/testing.md) for the tiers, markers and quality gates.

## CI/CD

GitHub Actions (`.github/workflows`) runs lint, the unit/graph/security/hygiene tiers, the PostgreSQL integration
tier, the coverage gate, and a nightly random-order flake check. Merges to `main` publish a container image to GHCR.
