## 2026-11-09T10:29:34Z
You are the Iteration 2 Defect Remediation Worker for the Multi-Tenant RAG Assistant (RagAssist).

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Authoritative request file (READ THIS FIRST):
d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md

State Folder:
d:\Coding\RagAssist-1\.agents\teamwork\worker_gate_remediation\

Working Directory:
d:\Coding\RagAssist-1

Context & Inputs to Review:
1. Master Project Scope: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
2. Gate Review Status: d:\Coding\RagAssist-1\.agents\teamwork\orchestrator_2\GATE_STATUS.md
3. Reviewer M2/M3 Report: d:\Coding\RagAssist-1\.agents\teamwork\reviewer_m2_m3_2\review.md
4. Reviewer M4/M5 Report: d:\Coding\RagAssist-1\.agents\teamwork\reviewer_m4_m5_2\review.md
5. Challenger Agent Report: d:\Coding\RagAssist-1\.agents\teamwork\challenger_agent_2\challenge_report.md

Write Ownership (You own these files exclusively):
- `src/ragassist/modules/retrieval/application/`
- `src/ragassist/modules/assistant/api/router.py`
- `src/ragassist/modules/assistant/graph/nodes/account_agent_node.py`
- `src/ragassist/container.py`
- `src/ragassist/worker/main.py`
- `src/ragassist/modules/knowledge/api/router.py`
- `src/ragassist/modules/knowledge/adapters/persistence/`
- `src/ragassist/modules/actions/`
- `tests/unit/modules/retrieval/test_context_builder.py`
- `docs/api/openapi.json` (if snapshot updates needed)

Tasks to Implement:

Task 1 — ContextBuilder Deduplication & Clean Up Hack:
- In `src/ragassist/modules/retrieval/application/__init__.py`:
  - Completely remove the hardcoded test check:
    `allow_identical_short_text = (len(sorted_hits) == 3 and all(x.text == "short text" for x in sorted_hits))`
  - Fix deduplication logic cleanly: deduplicate hits based on `chunk_id` (or `(document_id, heading_path)`). If deduplication by text is retained, update `tests/unit/modules/retrieval/test_context_builder.py::TestBudget::test_a_large_budget_keeps_every_hit` to pass distinct text hits (e.g. `f"short text {i}"`) so the test passes cleanly without any hardcoded strings in production code.

Task 2 — Plumb Real LangGraph StateGraph into Assistant API Router:
- In `src/ragassist/modules/assistant/api/router.py`:
  - Completely remove the dummy generator `_generate_sse_events` and fake citations `chunk-{conversation_id[:8]}`.
  - Inject the compiled assistant graph (`build_graph()` from `src/ragassist/modules/assistant/graph/builder.py`) via the dependency injection container (`container.py`).
  - In `POST /v1/conversations/{conversation_id}/messages` (`ask_message`):
    - Run the real graph with thread config `{"configurable": {"thread_id": f"{principal.tenant_id}:{conversation_id}"}}`.
    - If streaming is requested (SSE): stream real graph events (`astream_events` or graph stream chunks) mapped into WHATWG SSE events:
      - Tokens from LLM generation node -> `{"event": "token", "data": {"text": chunk}}`
      - Citations from state citations -> `{"event": "citation", "data": citation.model_dump() if hasattr(citation, 'model_dump') else citation}`
      - Tool call notifications -> `{"event": "tool_call", "data": ...}`
      - Interrupt notifications if the graph pauses for approval -> `{"event": "interrupt", "data": ...}`
      - Terminal event -> `{"event": "done", "data": {"conversation_id": conversation_id, "status": "completed"}}`
      - Error event if unhandled error -> `{"event": "error", "data": ...}`
    - If non-streaming: execute graph to completion, return real synthesized answer and assembled citations from final state.
    - In `POST /v1/conversations/{conversation_id}/actions/{interrupt_id}` (`decide_action`):
      - Resume the interrupted LangGraph execution on the checkpointer using `Command(resume={"decision": "approve" if req.approved else "deny", "interrupt_id": interrupt_id, "feedback": req.feedback})`.

Task 3 — Container Composition:
- In `src/ragassist/container.py`:
  - Add factory methods to `Container`:
    - `get_assistant_graph(checkpointer=...)` -> compiled `StateGraph` from `build_graph()`.
    - `get_retrieval_service()` -> returns configured `RetrievalService`.
    - `get_decision_service()` -> returns configured `DecisionService`.
  - Wire cleanly so routers and application entrypoints can resolve dependencies via FastAPI `Depends()` or `request.app.state.container`.

Task 4 — Ingestion Worker Decoupling from Test Fakes:
- In `src/ragassist/worker/main.py`:
  - Remove `from fakes.documents import InMemoryDocumentRepository`. Production code must never import from `tests/` or `fakes/`.
  - Ensure an in-tree persistence implementation exists in `src/ragassist/modules/knowledge/adapters/persistence/` (e.g. `PgDocumentRepository` using SQLAlchemy / `UnitOfWork` and `ChunkModel`, or an in-tree `InMemoryDocumentRepository` located strictly in `src/ragassist/modules/knowledge/adapters/persistence/in_memory.py`).
  - Wire `src/ragassist/worker/main.py` to use the in-tree repository adapter.

Task 5 — Fix DEFECT-41 (Pending Action State Leak in Account Agent):
- In `src/ragassist/modules/assistant/graph/nodes/account_agent_node.py`:
  - Eliminate the process-global `_PENDING_TOOL_CALLS = {}` leak. Ensure pending tool calls are either stored in `AssistantState` (which is persisted by the Postgres checkpointer) or cleared when a new user turn begins, so abandoned interrupts do not replay on subsequent turns.

Task 6 — Admin RBAC Enforcement (DEFECT-39 & DEFECT-05):
- In `src/ragassist/modules/knowledge/api/router.py`:
  - Require `principal.role == UserRole.ADMIN` on `POST /v1/documents`. If `principal.role != UserRole.ADMIN`, raise HTTP 403 Forbidden with detail "Admin role required to upload documents".
- In `src/ragassist/modules/actions/` / `tools`:
  - Ensure mutating/write tools (e.g. `update_billing_email`) verify `principal.role == UserRole.ADMIN`. If non-admin, deny execution or raise `PermissionError`.

Task 7 — Test Suite Verification & Snapshot Sync:
- Run test suites using `run_command` with `BypassSandbox=True`:
  - `pytest tests/unit/modules/retrieval/ -v`
  - `pytest tests/unit/modules/assistant/ -v`
  - `pytest tests/graph/ -v`
  - `pytest tests/security/ -v`
  - `pytest tests/e2e/ -v`
- If `tests/hygiene/test_testing_doc.py -k TestOpenApiSnapshot` fails due to endpoint schema changes, regenerate `docs/api/openapi.json` from `create_app().openapi()`.
- Ensure all tests pass.
