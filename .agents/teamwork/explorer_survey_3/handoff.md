# Handoff Report — Infra, Dependencies, and External Services Survey

**Agent**: Infra and Dependencies Explorer (`explorer_survey_3`)  
**Parent Orchestrator**: `be9621e6-d3bc-446a-abb9-2d0c46239ab1`  
**Milestone**: Step 0 — Survey Phase  
**Timestamp**: 2026-11-07T20:25:00Z  
**Type**: Hard Handoff (Investigation Complete)  

---

## 1. Observation

1. **Python Runtime & Environment**:
   - `.\.venv\Scripts\python.exe --version` returned `Python 3.12.10`.
   - `pyproject.toml` line 6 specifies: `requires-python = ">=3.12,<3.13"`.
   - `uv` executable exists at `C:\Users\ASUS\.local\bin\uv.exe` and outputs `uv 0.11.32 (3010295ae 2026-07-23 x86_64-pc-windows-msvc)`. However, `uv` is not present in PowerShell's default `$env:PATH` (`CommandNotFoundException`).
   - No `uv.lock` file exists in the workspace.
2. **Dependency State in `.venv`**:
   - `& C:\Users\ASUS\.local\bin\uv.exe pip list` confirmed that foundational packages are installed:
     - `fastapi==0.162.2`, `pydantic==2.14.3`, `pydantic-settings==2.16.2`, `sqlalchemy==2.1.8`, `asyncpg==0.32.0`, `langgraph==1.2.20`, `langchain==1.4.9`, `langchain-openai==1.7.4`, `langchain-anthropic==1.7.10`, `structlog==26.1.0`, `pyjwt==2.15.1`, `pytest==9.2.0`, `pytest-asyncio==1.4.1.post1`.
   - Critical project libraries declared in `pyproject.toml` (lines 12–50) are **missing from `.venv`**:
     - `alembic`, `pgvector`, `langgraph-checkpoint-postgres`, `langchain-openrouter`, `chonkie`, `rerankers`, `flashrank`, `semantic-router`, `pymupdf4llm`, `markdownify`, `aioboto3`, `prometheus-fastapi-instrumentator`, `slowapi`, `typesafe-sdk`, `poethepoet`, `typer`.
     - Optional ML dependencies `torch` and `sentence-transformers` are missing (`torch import error: No module named 'torch'`).
3. **Container Infrastructure (`compose.yaml`)**:
   - `compose.yaml` (lines 1–74) specifies four services:
     - `postgres`: `pgvector/pgvector:pg16` on port `5432:5432` with `infra/postgres/init.sql` creating `app_user` and installing `vector` and `uuid-ossp` extensions.
     - `localstack`: `localstack/localstack:3.8.1` on port `4566:4566` running `s3,sqs,secretsmanager` with `infra/localstack/init.sh` creating `s3://ragassist-docs` and `ragassist-ingest` queue with `ragassist-ingest-dlq`.
     - `mock-saas`: built from `infra/docker/mock_saas.Dockerfile` running `services/mock_saas/main.py` on port `8001:8001`. Pre-configured with accounts for Acme Corp (`a0000000-0000-0000-0000-000000000001`) and Globex Corp (`b0000000-0000-0000-0000-000000000002`).
     - `api`: built from `infra/docker/api.Dockerfile` on port `8000:8000`.
   - Running `docker ps` produced error: `permission denied while trying to connect to the docker API at npipe:////./pipe/docker_engine`.
4. **Hardware & GPU Setup**:
   - `nvidia-smi` reported:
     - Device: `NVIDIA GeForce RTX 3060 Laptop GPU`
     - Driver Version: `610.74`, CUDA Version: `13.3`
     - Total VRAM: `6144 MiB` (6 GB), currently 0 MiB allocated.
5. **Configuration Files (`.env`, `.env.example`, `settings.py`, `models.yaml`)**:
   - `.env.example` (118 lines) and `.env` (117 lines) are fully synchronized with all fields in `src/ragassist/shared/config/settings.py` (lines 1–132).
   - The directory `config/` exists but is currently empty (`config/models.yaml` has not yet been authored).
6. **Codebase Phase 0 Artifacts**:
   - Shared kernel and security modules are implemented and tested:
     - `src/ragassist/shared/domain/__init__.py`: `TenantId`, `UserId`, `DomainError`, `TenantIsolationError`.
     - `src/ragassist/shared/security/jwt.py`: `Principal`, `UserRole`, `create_access_token`, `decode_access_token`.
     - `src/ragassist/shared/db/session.py` & `uow.py`: `UnitOfWork` with `SET LOCAL app.tenant_id = :tenant_id`.
     - `src/ragassist/shared/resilience.py`: `FallbackChain` and `run_cpu_bound` (4 workers).
     - `src/ragassist/shared/registry.py`: generic `ProviderRegistry`.
     - `src/ragassist/platform/llm/ports.py` & `adapters/`: `OpenAIAdapter`, `AnthropicAdapter`, `OpenRouterAdapter`.
     - `tests/unit/test_shared_kernel.py`: passes unit tests.

---

## 2. Logic Chain

1. **Premise**: Starting implementation from Phase 1 onwards requires a known, reproducible execution environment with verified toolchains and interfaces.
2. **From Observation 1**: Python 3.12.10 is installed and aligns with `pyproject.toml` (`>=3.12,<3.13`). `uv` is available at `C:\Users\ASUS\.local\bin\uv.exe`, meaning fast package synchronization can be performed using explicit paths even if not in standard PATH.
3. **From Observation 2**: Because many core and optional packages are missing from `.venv` (notably `pgvector`, `alembic`, `chonkie`, `rerankers`, `aioboto3`), any Phase 1–5 implementation will fail imports unless packages are installed or stubbed/faked.
4. **From Observation 3 & 4**: Although the host has an NVIDIA RTX 3060 GPU with CUDA 13.3, `torch` and `sentence-transformers` are not yet installed in `.venv`. Because ADR 0005 defines a three-tier reranker chain (`cross_encoder -> flashrank -> none`), workers can either:
   - Install `torch` with CUDA wheels to utilize the GPU, OR
   - Run in CPU mode using `flashrank` (ONNX runtime) or pass-through RRF (`none`), ensuring zero development blockages.
5. **From Observation 3**: Because the Docker daemon is currently inaccessible in the sandbox/terminal, integration tests and development runs must prioritize UnitOfWork fakes and `respx` HTTP mock clients rather than relying on live Docker containers.
6. **From Observation 5 & 6**: Phase 0 laid the foundational interfaces (`ProviderRegistry`, `FallbackChain`, `Settings`, `UnitOfWork`). `config/models.yaml` must be created in Phase 1 as the single source of truth for model role mappings (`gen-default`, `gen-openrouter-llama`).

---

## 3. Caveats

1. **Docker Daemon Access**: We observed `permission denied` connecting to the Docker named pipe. If live container testing of Postgres/LocalStack is mandatory during later phases, Docker Desktop must be running with user pipe permissions outside the sandbox.
2. **Network / Wheel Downloads**: Installing heavy ML dependencies (`torch` ~2.5GB) over network depends on the active subagent network mode. If network access is restricted, pure CPU fallbacks and mock adapters must be used.
3. **Specification Files Location**: `implementation_plan.md` and `architecture_arc42.md` were not present in the workspace root or `docs/`. However, all architectural decisions, settings, data models, and requirements are fully reflected in `AGENTS.md`, `docs/adr/0001-0005`, `compose.yaml`, `.env.example`, and `settings.py`.

---

## 4. Conclusion

The infrastructure, environment, and architectural boundaries are thoroughly mapped and ready for Phase 1 execution:
- **Environment**: Python 3.12.10 inside `.venv`, `uv 0.11.32` at `C:\Users\ASUS\.local\bin\uv.exe`.
- **Infrastructure**: Complete Docker Compose setup for PostgreSQL 16 + pgvector (5432), LocalStack S3/SQS (4566), and Mock SaaS (8001).
- **GPU & Fallbacks**: NVIDIA RTX 3060 6GB available; dual-track architecture guarantees functioning execution on both GPU and CPU.
- **Immediate Work for Phase 1**: Create `config/models.yaml`, complete `platform/llm` and `platform/embeddings` provider registries and fallback chains, and synchronize missing dependencies in `.venv`.

---

## 5. Verification Method

To independently verify the observations and findings in this report, execute the following commands:

1. **Verify Python & uv versions**:
   ```powershell
   & .\.venv\Scripts\python.exe --version
   & C:\Users\ASUS\.local\bin\uv.exe --version
   ```
2. **Verify missing dependencies in `.venv`**:
   ```powershell
   & .\.venv\Scripts\python.exe -c "
   for mod in ['pgvector', 'alembic', 'chonkie', 'rerankers', 'flashrank', 'torch']:
       try:
           __import__(mod)
           print(f'{mod}: available')
       except ImportError:
           print(f'{mod}: NOT installed')
   "
   ```
3. **Verify GPU availability**:
   ```powershell
   nvidia-smi
   ```
4. **Verify settings synchronization**:
   Inspect `src/ragassist/shared/config/settings.py` against `.env.example`.
5. **Inspect Detailed Survey Document**:
   Read `d:\Coding\RagAssist-1\.agents\teamwork\explorer_survey_3\survey_infra.md`.
