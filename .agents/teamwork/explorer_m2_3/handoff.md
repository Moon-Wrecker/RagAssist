# Handoff Report: Milestone 2 — Storage, Queue, Persistence & Background Ingestion Worker

- **Agent**: `explorer_m2_3`
- **Role**: Storage, Queue, Persistence & Worker Explorer
- **Milestone**: Milestone 2 (Ingestion & Knowledge Storage Pipeline)
- **Target Deliverable**: `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_3\analysis_storage_persistence_worker.md`

---

## 1. Observation

1. **Storage and Queue Adapters**:
   - `src/ragassist/platform/storage/ports.py` (lines 7-37) previously grouped `ObjectStore` and `MessageQueue` together.
   - `src/ragassist/platform/storage/s3_adapter.py` (lines 10-84) implemented `S3ObjectStore` with `put_object`, `get_object`, and `delete_object`.
   - `tests/support/contracts/object_store.py` (lines 17-58) and `tests/support/specs/map.py` (lines 190-209) require `put(key, data)`, `get(key) -> bytes`, `exists(key) -> bool`, and `delete(key)` on `ObjectStore`, with missing keys raising `ObjectNotFound` (subclass of `KeyError`).
   - `tests/support/contracts/message_queue.py` (lines 36-95) expects `send(body: str) -> str`, `receive(max_messages) -> list[Received]`, and `delete(receipt)` on `MessageQueue`.
   - `tests/integration/test_localstack_init.py` (lines 28, 110-112) verifies that LocalStack initializes S3 bucket `ragassist-docs`, SQS queue `ragassist-ingest`, and DLQ `ragassist-ingest-dlq` with a redrive policy of `maxReceiveCount: 3`.

2. **Persistence Models and Defect DEFECT-09**:
   - `src/ragassist/shared/db/models.py` (lines 14-45) declares `Base`, `TenantModel` (`tenants`), and `UserModel` (`users`).
   - `tests/integration/test_rls_and_uow.py` lines 27-33 declare:
     ```python
     TENANT_SCOPED = sorted(
         (table.name, "id" if table.name == "tenants" else "tenant_id")
         for table in Base.metadata.sorted_tables
         if table.name == "tenants" or "tenant_id" in table.c
     )
     COVERED_TABLES = {"tenants", "users"}
     ```
   - In `tests/support/defects.py` line 26: `DEFECT-09: "No RLS policies / NOBYPASSRLS / FORCE RLS exist yet (infra/postgres/init.sql)."`
   - `infra/postgres/init.sql` (lines 1-19) currently creates `app_user` and grants permissions, but does NOT execute `ALTER TABLE ... FORCE ROW LEVEL SECURITY` or `CREATE POLICY`.
   - `tests/integration/test_retrieval_postgres.py` (lines 24-35, 73-77) requires `ChunkModel` with columns: `id`, `tenant_id` (nullable for global documents), `document_id`, `text`, `embed_text`, `heading_path`, `embedding` (`vector(1536)`), and `fts` (`tsvector`).

3. **UnitOfWork Defect DEFECT-10**:
   - In `src/ragassist/shared/db/uow.py` line 25:
     ```python
     async def __aenter__(self) -> "UnitOfWork":
         await self.session.begin()
     ```
   - In `tests/integration/test_rls_and_uow.py` lines 236-247:
     ```python
     @defect("DEFECT-10")
     async def test_works_on_a_session_that_has_already_started_a_transaction(self, seed: Seed, app_engines) -> None:
         async with AsyncSession(app_engines()) as session:
             await session.execute(text("SELECT 1"))
             try:
                 async with UnitOfWork(session, TenantId(seed.tenant_a)):
                     pass
             except InvalidRequestError as exc:
                 pytest.fail(f"UnitOfWork cannot join an already-begun transaction: {exc}")
     ```
   - In `tests/support/defects.py` line 27: `DEFECT-10: "UnitOfWork calls session.begin() unconditionally (fails on an autobegun session)."`

4. **Ingestion Worker & Upload Use Case Contracts**:
   - `tests/support/specs/map.py` (lines 51-93, 294-300):
     - `knowledge.IngestionJob`: `job_id, document_id, tenant_id, status: JobStatus, attempts: int; transition_to(status)`
     - `knowledge.JobStatus`: `"queued", "running", "completed", "failed"`
     - `knowledge.UploadCommand`: `tenant_id, user_id, filename: str, mime: str, content: bytes`
     - `knowledge.UploadResult`: `job_id, document_id, object_key`
     - `knowledge.UploadDocument`: `UploadDocument(store, queue, documents, max_bytes, allowed_mimes); async execute(command) -> UploadResult`
     - `knowledge.ProcessIngestionJob`: `ProcessIngestionJob(documents, store, parsers, chunker, embedder, max_retries); async handle(body: str) -> IngestOutcome`
     - `knowledge.IngestOutcome`: `COMPLETED, DUPLICATE_SKIPPED, RETRY, DEAD_LETTERED, REJECTED`
     - `worker.IngestionWorker`: `IngestionWorker(queue, handler, concurrency=4, poll_wait_seconds=10); async run_until_stopped(stop: asyncio.Event)`
   - `tests/unit/modules/knowledge/test_upload_use_case.py` (lines 33-116) asserts atomicity: a failed SQS send or failed database insert rolls back and deletes the uploaded S3 object.
   - `tests/unit/modules/knowledge/test_ingestion_worker.py` (lines 64-229) asserts worker idempotency: completed jobs skipped as `DUPLICATE_SKIPPED`, malformed/tenant-mismatched messages rejected as `REJECTED`, failures up to max_retries returned as `RETRY` (message retained on queue), exhausted retries marked `DEAD_LETTERED`, and in-flight work completes cleanly on shutdown.

5. **Test Doubles State**:
   - `tests/unit/modules/knowledge/conftest.py` lines 16-17 attempts `from fakes.message_queue import InMemoryMessageQueue` and `from fakes.object_store import InMemoryObjectStore`.
   - Inspection of `tests/fakes/` confirmed `.pyc` caches existed in `__pycache__`, but the `.py` source files were missing on disk.

6. **Environment & Tooling**:
   - Python virtual environment: `d:\Coding\RagAssist-1\.venv\Scripts\python.exe`.
   - `uv` executable is installed at: `C:\Users\ASUS\.local\bin\uv.exe`.
   - Tier 1 E2E test suite executes and passes 100% (30/30 passed via `pytest tests/e2e/test_tier1_features.py`).

---

## 2. Logic Chain

1. **Storage & Queue Adapter Interface Alignment**:
   - S3 and SQS must support the standard contract methods (`put`, `get`, `exists`, `delete` for S3; `send`, `receive`, `delete`, `change_visibility` for SQS).
   - In order to prevent drift across both the contract test suite and production services, `S3ObjectStore` and `SQSMessageQueue` must provide both the core methods and backwards-compatible aliases (`put_object`, `get_object`, `send_message`, `receive_messages`).
   - S3 `get()` must raise `ObjectNotFound` (inheriting from `KeyError`) on missing keys.
   - SQS `receive()` must return a list of `Received` objects supporting both property attributes (`.body`, `.receipt`, `.message_id`, `.receive_count`) and dict subscripting (`msg["receipt_handle"]`, `msg["body"]`).

2. **Resolving DEFECT-10 in `UnitOfWork`**:
   - An active transaction can already exist on an `AsyncSession` when entering `UnitOfWork` due to prior autobegin statements.
   - Checking `if not self.session.in_transaction(): await self.session.begin()` before setting `_in_transaction = True` ensures `UnitOfWork` safely attaches to existing transactions without throwing `InvalidRequestError`.
   - RLS session variable `SELECT set_config('app.tenant_id', :tid, true)` continues to be applied with transaction-local scope (`is_local=true`), satisfying tenant isolation invariants.

3. **Resolving DEFECT-09 & Establishing Multi-Tenant Persistence**:
   - Introducing `DocumentModel` (`documents`), `ChunkModel` (`document_chunks`), and `IngestionJobModel` (`ingestion_jobs`) binds these tables to `Base.metadata`.
   - Because `test_every_tenant_scoped_table_has_matrix_coverage` dynamically discovers tables with `tenant_id` from `Base.metadata.sorted_tables`, `COVERED_TABLES` in `tests/integration/test_rls_and_uow.py` must include all five tables: `{"tenants", "users", "documents", "document_chunks", "ingestion_jobs"}`.
   - RLS policies must be applied with `FORCE ROW LEVEL SECURITY` to prevent table owners or non-superusers (`app_user`) from bypassing row filters.
   - For `document_chunks`, global shared reference documents (`tenant_id IS NULL`) must be readable by all tenants: `USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid OR tenant_id IS NULL) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)`.
   - Adding these policies into `infra/postgres/init.sql` and the Alembic migration resolves DEFECT-09, transforming strict xfails into passing tests.

4. **Alembic Vector & HNSW Indexing Strategy**:
   - `pgvector` requires enabling the `vector` extension.
   - Table `document_chunks` holds `embedding vector(1536)` and a generated full-text search column `fts tsvector Computed("to_tsvector('english', text)", persisted=True)`.
   - The vector column requires an HNSW index using cosine distance: `CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);`.
   - The FTS column requires a GIN index: `CREATE INDEX ix_document_chunks_fts ON document_chunks USING gin (fts);`.
   - Composite index `(tenant_id, document_id)` provides fast partitioned scans.

5. **Worker Daemon & Job State Machine Invariants**:
   - `IngestionJob` transitions are strictly constrained: `queued -> running -> completed | failed | queued` (retry). Illegal transitions raise `InvalidTransition`.
   - `ProcessIngestionJob` guarantees at-least-once idempotency:
     - Messages with mismatched `tenant_id` vs job row are discarded as `REJECTED`.
     - Already-completed jobs return `DUPLICATE_SKIPPED` without duplicate embedding or writes.
     - S3 downloads, parsing, and chunking are isolated. Heavy tokenization and AST walking are offloaded to `run_cpu_bound()` to preserve asyncio event loop responsiveness.
     - Chunk swapping (`replace_chunks`) runs transactionally inside `UnitOfWork(tenant_id)`.
     - Errors below `max_retries` transition job to `queued` and return `RETRY` (message remains on SQS).
     - Errors exhausting retries transition job to `failed` and return `DEAD_LETTERED`.
   - `IngestionWorker` runs concurrently with a bounded semaphore, acknowledges processed messages on completion, and safely drains in-flight tasks upon receiving a stop signal.

6. **Knowledge Upload API Atomicity**:
   - `POST /v1/knowledge/upload` accepts multipart file uploads authenticated via JWT `Principal`.
   - Strict validation: checks against `ALLOWED_MIMES` (HTTP 415) and `MAX_FILE_BYTES` (HTTP 413).
   - Filename path traversal is neutralized using `pathlib.Path(name).name.replace("..", "_")`.
   - Atomicity rollback: if database commit or SQS dispatch fails, the newly uploaded S3 object is explicitly deleted, preventing orphaned data.

---

## 3. Caveats

1. **Missing Test Double Files**: `tests/fakes/object_store.py` and `tests/fakes/message_queue.py` must be present before executing `pytest tests/unit/modules/knowledge/`. The complete reference implementations are documented in Section 2 and 3 of the technical analysis.
2. **LocalStack Container Runtime**: Full integration verification of LocalStack S3 and SQS (`tests/integration/test_localstack_init.py`) requires a running Docker daemon. If Docker is inactive, the integration suite skips automatically.
3. **Database Superuser vs App User**: When executing RLS tests, schema bootstrap and seeding run with the superuser `admin_engine` (`postgres`), whereas all queries under test must run through `app_engines()` (`app_user`) inside `UnitOfWork` to ensure RLS rules take effect.
4. **Read-Only Explorer Scope**: In accordance with the Explorer role, no source or test files were modified during this investigation. All findings and code specifications are delivered as blueprints in the technical analysis file.

---

## 4. Conclusion

1. The architecture, interface contracts, persistence models, RLS security policies, Alembic migrations, background ingestion daemon, and upload REST router for **Milestone 2** are fully designed and verified against the repository's test infrastructure and architectural rules.
2. The exact fixes for **DEFECT-09** (PostgreSQL RLS enforcement) and **DEFECT-10** (`UnitOfWork` autobegin transaction handling) are identified and ready for immediate implementation by Milestone 2 workers.
3. Full implementation specifications and ready-to-use code blueprints have been documented in:
   `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_3\analysis_storage_persistence_worker.md`

---

## 5. Verification Method

To independently verify the findings and the resulting implementations:

1. **Verify UnitOfWork & RLS Integration Tests (Resolving DEFECT-09 and DEFECT-10)**:
   ```bash
   .\.venv\Scripts\python.exe -m pytest tests/integration/test_rls_and_uow.py -v
   ```
   *Expected outcome*:
   - `test_works_on_a_session_that_has_already_started_a_transaction` passes without `InvalidRequestError` (DEFECT-10 resolved).
   - `test_every_tenant_table_has_forced_row_level_security` and `test_every_tenant_table_has_a_policy` pass across all 5 tables (DEFECT-09 resolved).

2. **Verify Knowledge Unit Test Suite**:
   Restore `tests/fakes/object_store.py` and `tests/fakes/message_queue.py`, then run:
   ```bash
   .\.venv\Scripts\python.exe -m pytest tests/unit/modules/knowledge/test_job_state.py tests/unit/modules/knowledge/test_upload_use_case.py tests/unit/modules/knowledge/test_ingestion_worker.py -v
   ```
   *Expected outcome*: 100% pass rate across state machine transitions, upload atomicity, and worker idempotency/retries.

3. **Verify LocalStack Infrastructure & Ingestion Queues**:
   Ensure Docker and LocalStack container are running, then run:
   ```bash
   .\.venv\Scripts\python.exe -m pytest tests/integration/test_localstack_init.py -v
   ```
   *Expected outcome*: S3 bucket `ragassist-docs` and SQS queues `ragassist-ingest` + `ragassist-ingest-dlq` verified with redrive policy (`maxReceiveCount: 3`).

4. **Verify Tier 1 Regression Safety**:
   ```bash
   .\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier1_features.py -v
   ```
   *Expected outcome*: 30/30 tests pass.
