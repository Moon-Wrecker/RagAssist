# DISPATCH — worker_m2

- **Role**: Milestone 2 Implementer (Ingestion & Knowledge Storage Pipeline)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\worker_m2
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md

## Exclusive Write Ownership
You have exclusive write ownership over:
- `src/ragassist/platform/storage/` (S3 client)
- `src/ragassist/platform/queue/` (SQS client)
- `src/ragassist/modules/knowledge/` (parsers, chunker, models, repositories, upload API)
- `src/ragassist/worker/ingestion_worker.py` (background daemon)
- `alembic/versions/` (migration for documents & chunks)
- `tests/unit/test_parsers.py`, `tests/unit/test_chunker.py`, `tests/integration/test_rls_and_uow.py`

DO NOT modify files outside your write ownership (e.g., `platform/llm/`, `platform/decisions/`, `modules/retrieval/`, `modules/actions/`, `modules/assistant/`).

## Task Instructions
1. Implement S3 client (`src/ragassist/platform/storage/s3.py`) using `aioboto3` for bucket `ragassist-docs` (upload stream, download, exists, presigned URL).
2. Implement SQS client (`src/ragassist/platform/queue/sqs.py`) using `aioboto3` for queue `ragassist-ingest` and DLQ `ragassist-ingest-dlq`.
3. Implement multi-format document parsers in `src/ragassist/modules/knowledge/parsers/`:
   - `PDFParser` using `pymupdf4llm` preserving tables and page numbers.
   - `HTMLParser` using `markdownify` preserving headings and tables.
   - `MarkdownParser` and `PlainTextParser`.
   - Wrap CPU-bound parsing with `run_cpu_bound()` from `ragassist.shared.resilience`.
4. Implement 5-pass structure-aware `HybridChunker` in `src/ragassist/modules/knowledge/chunking/`:
   - Pass 1: AST Structural Splitting.
   - Pass 2: Table Protection (tables not split mid-row; large tables split with repeated header rows).
   - Pass 3: Contextual Breadcrumb Enrichment (`heading_path`).
   - Pass 4: Token Budgeting (target ~512 tokens using tiktoken safely).
   - Pass 5: Sibling Merging (merge short adjacent sections under same header).
   - Wrap CPU-bound tokenization with `run_cpu_bound()`.
5. Implement SQLAlchemy 2.0 models for `documents` and `document_chunks` with `vector(1536)` in `src/ragassist/modules/knowledge/adapters/persistence/models.py`.
   - Implement PostgreSQL Row-Level Security (RLS) policies for tenant isolation.
   - Implement Knowledge repository with UnitOfWork integration.
6. Implement background ingestion worker daemon (`src/ragassist/worker/ingestion_worker.py`).
7. Implement Knowledge upload REST API router (`src/ragassist/modules/knowledge/api/router.py`).
8. Add/verify unit tests for parsers, chunker, and RLS integration (`tests/integration/test_rls_and_uow.py` resolving DEFECT-09/DEFECT-10). Use `BypassSandbox=True` when invoking pytest on Windows.
9. Write `changes.md` and `handoff.md` in `d:\Coding\RagAssist-1\.agents\teamwork\worker_m2\`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.


## 2026-11-08T09:04:19Z
[Message from parent]
Milestone 2 Implementer: Ingestion & Knowledge Storage Pipeline for project RagAssist.
Execute M2 scope:
- S3 Client (`src/ragassist/platform/storage/s3.py`)
- SQS Client (`src/ragassist/platform/queue/sqs.py`)
- Document AST Parsers (`src/ragassist/modules/knowledge/parsers/`)
- 5-Pass Structure-Aware HybridChunker (`src/ragassist/modules/knowledge/chunking/`)
- Persistence Models & RLS (`src/ragassist/modules/knowledge/adapters/persistence/models.py`)
- Alembic Migration
- Background Ingestion Worker (`src/ragassist/worker/ingestion_worker.py`)
- Knowledge Upload REST Router (`src/ragassist/modules/knowledge/api/router.py`)
- Fix DEFECT-09 and DEFECT-10 in `tests/integration/test_rls_and_uow.py`
