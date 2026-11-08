# Task Assignment: M2–M5 Defect Remediation & Layout Harmonization

Target: Remediate isolated defects, resolve all test failures, add missing layout artifacts (container.py, cli/main.py, openapi.json), and verify 100% test pass.
Original Request: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
Project Spec: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
Working Directory: d:\Coding\RagAssist-1
State Folder: d:\Coding\RagAssist-1\.agents\teamwork\worker_remediation_m2_m5\
Explorer Reports to Consult:
- d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_m3_scan_2\handoff.md
- d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_m3_scan_2\analysis_m2_m3.md
- d:\Coding\RagAssist-1\.agents\teamwork\explorer_m4_m5_scan_2\handoff.md
- d:\Coding\RagAssist-1\.agents\teamwork\explorer_m4_m5_scan_2\analysis_m4_m5.md
- d:\Coding\RagAssist-1\.agents\teamwork\explorer_full_scan_2\handoff.md
- d:\Coding\RagAssist-1\.agents\teamwork\explorer_full_scan_2\full_test_scan.md


## 2026-11-08T18:49:19Z
You are a Worker agent assigned to remediate defects, fix all failing tests, and complete layout artifacts across Milestones 2 through 5.
Working directory: d:\Coding\RagAssist-1
State folder: d:\Coding\RagAssist-1\.agents\teamwork\worker_remediation_m2_m5\

MANDATORY FIRST STEP: Read d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md, d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md, and the explorer handoff reports:
- d:\Coding\RagAssist-1\.agents\teamwork\explorer_m2_m3_scan_2\handoff.md
- d:\Coding\RagAssist-1\.agents\teamwork\explorer_m4_m5_scan_2\handoff.md
- d:\Coding\RagAssist-1\.agents\teamwork\explorer_full_scan_2\handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope & Specific Tasks:
1. Fix Tool Abuse Handling & Concurrency Contamination:
   - In `src/ragassist/modules/assistant/graph/nodes/account_agent_node.py`:
     Check if tool is recognized in `tools` before calling `is_write()`. If unrecognized, create a tool result message rejecting the unknown tool rather than crashing. Wrap execution in a `try...finally` ensuring `_PENDING_TOOL_CALLS.pop(thread_key, None)` is cleaned up if an exception occurs so it does not pollute subsequent turns.
   - In `tests/fakes/tools.py`:
     In `RecordingToolRegistry.is_write(self, name: str)`: safely use `self._tools.get(name)` (returning False if None or not write) instead of `self._tools[name].write` which throws KeyError.
   - Verify `pytest tests/security/test_authz_and_tool_abuse.py -v` passes 100%.

2. Generate OpenAPI Snapshot:
   - Generate `docs/api/openapi.json` from `create_app().openapi()` (e.g. run a short Python one-liner to dump JSON with indent=2).
   - Verify `pytest tests/hygiene/test_testing_doc.py -k "TestOpenApiSnapshot" -v` passes.

3. Fix NDCG Metric when gain is 0.0:
   - In `evals/metrics/retrieval.py::ndcg_at_k`:
     Handle dictionary gains properly when `isinstance(relevant, Mapping)`. An item with gain 0.0 should not be awarded binary 1.0 relevance.
   - Verify `pytest tests/unit/evals/test_metrics_vs_oracles.py -k "test_ndcg_matches_the_oracle" -v` passes.

4. Fix DEFECT-33 (Job State Transitions):
   - In `src/ragassist/modules/knowledge/domain/__init__.py`:
     Remove transitions containing `"running"` from `LEGAL_JOB_TRANSITIONS`.
   - Remove `@defect("DEFECT-33")` from `tests/unit/modules/knowledge/test_job_state.py::TestLegalTableIsConsistentWithTheStatuses::test_every_state_named_in_the_legal_table_is_a_job_status`.
   - Verify `pytest tests/unit/modules/knowledge/test_job_state.py -v` passes.

5. Fix DEFECT-40 (Ingestion Atomicity Rollback):
   - In `src/ragassist/modules/knowledge/application/ingestion_service.py:153-157`:
     Call `delete_object(object_key)` on store.
   - Remove `@defect("DEFECT-40")` from `tests/unit/modules/knowledge/test_upload_use_case.py::TestAtomicity`.
   - Verify `pytest tests/unit/modules/knowledge/test_upload_use_case.py -v` passes.

6. Fix DEFECT-32 (Storage/Queue Adapter Decoupling):
   - In `src/ragassist/platform/storage/s3_adapter.py` and `src/ragassist/platform/queue/sqs_adapter.py`:
     Safely import `aioboto3` (e.g. `try: import aioboto3 except ImportError: aioboto3 = None`) so in-memory adapters can be imported in offline unit test environments without AWS SDK.
   - Remove `@defect("DEFECT-32")` from `tests/unit/platform/storage/test_in_memory_adapters_import_cleanly.py`.
   - Verify `pytest tests/unit/platform/storage/test_in_memory_adapters_import_cleanly.py -v` passes.

7. Align M3 Public Facade:
   - In `src/ragassist/modules/retrieval/domain/__init__.py`:
     Add `RetrievedChunk(BaseModel)` matching PROJECT.md Section 4: `chunk_id: UUID`, `document_id: UUID`, `content: str`, `score: float`, `heading_path: str | None = None`, `page_number: int | None = None`, `metadata: dict[str, Any] = Field(default_factory=dict)`.
   - In `src/ragassist/modules/retrieval/application/__init__.py`:
     Add `RetrievalService(Protocol)` with `async def retrieve(self, tenant_id: TenantId, query: str, top_k: int = 6) -> list[RetrievedChunk]: ...`.
   - Verify `pytest tests/unit/modules/retrieval/test_retrieval_service_contract.py -v` passes.

8. Complete Layout Artifacts (Container & CLI):
   - Implement `src/ragassist/container.py` exposing the application container and dependency wire-ups.
   - Implement `src/ragassist/cli/main.py` using Typer with `serve` and `worker` commands.
   - Ensure `pyproject.toml` registers `ragassist = "ragassist.cli.main:app"`.

9. Verification:
   - Run: `.\.venv\Scripts\python.exe -m pytest tests/security/ tests/unit/ tests/hygiene/ tests/e2e/ -v` with `BypassSandbox=True`.
   - Ensure 0 test failures remain across the entire suite.
   - Maintain strict inward dependency rule (domain -> application -> adapters -> api).
   - Document all changes in `.agents/teamwork/worker_remediation_m2_m5/changes.md` and write a structured 5-component `handoff.md`.
   - Send completion message to parent.
