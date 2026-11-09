# Changes Log — M2–M5 Defect Remediation & Layout Harmonization

This document records all changes made during the remediation task.

### 1. Tool Abuse Handling & Concurrency Cleanup
- **File**: `src/ragassist/modules/assistant/graph/nodes/account_agent_node.py`
  - Replaced unsafe `tools.is_write(tool_name)` call with an explicit registry check across `.get()`, `._tools`, and `.schemas()`.
  - When tool is unrecognized, emits an error `ToolMessage` and executes model reply instead of raising `KeyError`.
  - Wrapped turn execution in `try...except GraphInterrupt: raise except Exception: _PENDING_TOOL_CALLS.pop(thread_key, None); raise` to ensure thread state cannot pollute subsequent turns upon unexpected failure while preserving LangGraph interrupt-resume cycle.
- **File**: `tests/fakes/tools.py`
  - Updated `RecordingToolRegistry.is_write(name)` to use `self._tools.get(name)` returning `False` when None instead of throwing `KeyError`.
  - Added `get(name)` helper.

### 2. OpenAPI Documentation Snapshot
- **File**: `docs/api/openapi.json`
  - Generated full OpenAPI 3.1.0 schema specification snapshot from `create_app().openapi()` (41,144 bytes).
  - Validates `tests/hygiene/test_testing_doc.py::TestOpenApiSnapshot`.

### 3. Retrieval Metrics nDCG Oracle Alignment
- **File**: `evals/metrics/retrieval.py`
  - Updated `ndcg_at_k` to handle `isinstance(relevant, Mapping)` graded gains directly rather than converting keys to a set and awarding binary 1.0 relevance to 0.0-gain items.
  - Added `mean_reciprocal_rank` helper accepting sequence of runs.

### 4. Job State Transitions (DEFECT-33)
- **File**: `src/ragassist/modules/knowledge/domain/__init__.py`
  - Removed invalid `"running"` transitions (`("queued", "running")`, `("running", "completed")`, `("running", "failed")`, `("running", "queued")`) from `LEGAL_JOB_TRANSITIONS` so that all states in legal transitions match `JobStatus` enum.
- **File**: `tests/unit/modules/knowledge/test_job_state.py`
  - Removed `@defect("DEFECT-33")` from `TestLegalTableIsConsistentWithTheStatuses::test_every_state_named_in_the_legal_table_is_a_job_status`.

### 5. Ingestion Atomicity Compensation (DEFECT-40)
- **File**: `src/ragassist/modules/knowledge/application/ingestion_service.py`
  - Updated upload failure rollback to call `delete_object(object_key)` on store (the method exposed by `ObjectStore` protocol and adapters) rather than undefined `.delete()`.
- **File**: `tests/unit/modules/knowledge/test_upload_use_case.py`
  - Removed `@defect("DEFECT-40")` from `TestAtomicity::test_a_failed_queue_send_removes_the_job_and_the_object` and `test_a_failed_job_insert_removes_the_object`.

### 6. Storage & Queue Adapter Decoupling (DEFECT-32)
- **File**: `src/ragassist/platform/storage/s3_adapter.py`
  - Safely imported `aioboto3` under `try...except (ImportError, ModuleNotFoundError, Exception): aioboto3 = None`, allowing in-memory adapters to be used in environments without AWS SDK.
- **File**: `src/ragassist/platform/queue/sqs_adapter.py`
  - Safely imported `aioboto3` under `try...except (ImportError, ModuleNotFoundError, Exception): aioboto3 = None`.
- **File**: `tests/unit/platform/storage/test_in_memory_adapters_import_cleanly.py`
  - Removed `@defect("DEFECT-32")` from `TestInMemoryAdaptersWithoutTheAwsSdk::test_the_in_memory_adapters_import_without_aioboto3`.

### 7. Retrieval Public Facade Alignment
- **File**: `src/ragassist/modules/retrieval/domain/__init__.py`
  - Added `RetrievedChunk(BaseModel)` matching PROJECT.md Section 4 interface contract (`chunk_id`, `document_id`, `content`, `score`, `heading_path`, `page_number`, `metadata`).
- **File**: `src/ragassist/modules/retrieval/application/__init__.py`
  - Added `RetrievalService(Protocol)` with `async def retrieve(self, tenant_id: TenantId, query: str, top_k: int = 6) -> list[RetrievedChunk]: ...`.

### 8. Layout Artifacts (Container & CLI)
- **File**: `src/ragassist/container.py`
  - Implemented application composition root and `Container` / `get_container()` providing unified singleton access to settings, storage, and queue adapters.
- **File**: `src/ragassist/cli/main.py`
  - Implemented Typer CLI with `serve` (FastAPI HTTP & SSE server) and `worker` (SQS ingestion worker) commands.
- **File**: `pyproject.toml`
  - Registered entry point `[project.scripts] ragassist = "ragassist.cli.main:app"`.
