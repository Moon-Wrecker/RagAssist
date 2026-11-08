# DISPATCH — explorer_m2_3

- **Role**: Storage, Queue, Persistence & Worker Explorer
- **Milestone**: Milestone 2 (Ingestion & Knowledge Storage Pipeline)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_3
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md
- **Implementation Plan**: d:\Coding\RagAssist-1\docs\arc42\ or implementation_plan.md

## Objective
Investigate and design the storage, queue, persistence models, and background ingestion pipeline:
1. S3 Storage Adapter (`src/ragassist/platform/storage/s3.py`): `aioboto3` client for bucket `ragassist-docs` (upload, download, stream, presigned URL).
2. SQS Queue Adapter (`src/ragassist/platform/queue/sqs.py`): `aioboto3` client for queue `ragassist-ingest` and DLQ `ragassist-ingest-dlq`.
3. Database Models & Schema (`src/ragassist/modules/knowledge/adapters/persistence/models.py`): SQLAlchemy 2.0 models for `documents` and `document_chunks` with `vector(1536)` column.
4. PostgreSQL Row-Level Security (RLS) on `documents` and `document_chunks` tables:
   - `CREATE POLICY ... ON documents FOR ALL USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);`
   - UnitOfWork verification (`tests/integration/test_rls_and_uow.py`, resolving DEFECT-09 and DEFECT-10).
5. Alembic Migration: Migration script to create tables, RLS policies, vector extension, and HNSW cosine index.
6. Background Ingestion Worker (`src/ragassist/worker/ingestion_worker.py`): Async polling daemon polling SQS, downloading from S3, invoking parser + hybrid chunker, generating embeddings via `EmbeddingProvider`, inserting chunks in batch inside `UnitOfWork`.
7. Knowledge Upload REST Router (`src/ragassist/modules/knowledge/api/router.py`): Streaming multipart upload, initial document state, SQS message dispatch.
8. Design test matrix for unit and integration testing.

Deliver technical analysis to `analysis_storage_persistence_worker.md` and summary in `handoff.md`.


## 2026-11-08T09:01:56Z
You are explorer_m2_3 (Storage, Queue, Persistence & Worker Explorer) for Milestone 2 (Ingestion & Knowledge Storage Pipeline) in project RagAssist.

CRITICAL INSTRUCTIONS:
1. You MUST read the original user request at:
   `d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md`
   before beginning work.
2. Read `d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md`, `d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md`, and `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_3\DISPATCH.md`.
3. Check existing codebase, especially:
   - `src/ragassist/platform/storage/` and `src/ragassist/platform/queue/`
   - `src/ragassist/shared/db/` (`base.py`, `session.py`, `uow.py`)
   - `src/ragassist/modules/knowledge/`
   - `src/ragassist/worker/`
   - `tests/integration/test_rls_and_uow.py` (review DEFECT-09 and DEFECT-10)
   - `compose.yaml` (LocalStack S3/SQS configuration, Postgres pgvector configuration)
   - `pyproject.toml` (aioboto3, sqlalchemy, pgvector, alembic).
4. You are a READ-ONLY explorer. DO NOT write or edit source code or test files. Only write your analysis and handoff report inside your state folder:
   `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_3\`
5. In your analysis:
   - Detail S3 Storage Adapter (`src/ragassist/platform/storage/s3.py`) using `aioboto3` for bucket `ragassist-docs` (upload stream, download, exists, presigned URL).
   - Detail SQS Queue Adapter (`src/ragassist/platform/queue/sqs.py`) using `aioboto3` for queue `ragassist-ingest` and DLQ `ragassist-ingest-dlq` (send_message, receive_messages, delete_message, change_visibility).
   - Detail PostgreSQL database models (`DocumentModel`, `DocumentChunkModel`) with SQLAlchemy 2.0 in `src/ragassist/modules/knowledge/adapters/persistence/models.py`.
   - Specify Row-Level Security (RLS) policies on `documents` and `document_chunks`:
     `CREATE POLICY tenant_isolation_documents ON documents FOR ALL USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);`
     `CREATE POLICY tenant_isolation_chunks ON document_chunks FOR ALL USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);`
     Address DEFECT-09 and DEFECT-10 in `tests/integration/test_rls_and_uow.py`.
   - Specify Alembic migration to create tables, enable RLS, add vector extension (`vector(1536)`), and add HNSW index (`USING hnsw (embedding vector_cosine_ops)`).
   - Detail Background Ingestion Worker daemon (`src/ragassist/worker/ingestion_worker.py`): message loop, polling SQS, downloading file from S3, invoking appropriate parser and hybrid chunker, generating embeddings via `EmbeddingProvider`, inserting documents and chunks transactionally via `UnitOfWork`.
   - Detail Knowledge Upload REST Router (`src/ragassist/modules/knowledge/api/router.py`): streaming multipart file upload, JWT Principal authentication, generating S3 object key, persisting initial `Document` status `PENDING`, enqueueing job to SQS.
   - Propose the exact file paths and interfaces adhering to the Modular Monolith architecture in `PROJECT.md`.
   - Provide a comprehensive test specification for storage/queue unit tests, worker tests, and RLS integration tests.
6. Write your detailed analysis to `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_3\analysis_storage_persistence_worker.md` and complete handoff report to `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_3\handoff.md`.
7. Once finished, send a message back to the orchestrator summarizing your findings and linking to your reports.
