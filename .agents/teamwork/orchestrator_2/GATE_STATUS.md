# Gate Status — Milestones 2–6

## Overview
- Milestone 1: DONE (Signed off in orchestrator_1/GATE_STATUS.md with Gate 2 PASS)
- Milestones 2–5: Populated by dedicated parallel builders. Undergoing baseline test execution, defect remediation, and Gate reviews.
- Milestone 6: Final Milestone (Tiers 1–4 E2E pass + Tier 5 Adversarial Coverage Hardening).

---

## Baseline Scan
- **Total Tests Collected**: 2,048
- **Passed**: 1,901 (92.8%)
- **Failed**: 2 (both in `tests/security/test_authz_and_tool_abuse.py`)
- **Skipped**: 75 (optional ML dependencies / offline DB containers)
- **XFailed**: 70 (strict defect markers)
- **E2E 4-Tier Test Suite**: 163 / 163 passed (100% pass rate)
- **Architecture & Layering**: 100% compliant with Hexagonal Inward Dependency Rule (`check_tree(SRC_ROOT)` passed with 0 violations)
- **Action Plan**: Dispatch Worker `worker_remediation_m2_m5` to fix tool abuse handling, generate OpenAPI snapshot, resolve NDCG oracle metric, clean up DEFECT-33/40/32, expose M3 `RetrievalService`/`RetrievedChunk`, and add `container.py` and `cli/main.py`.

---

## Gate — Milestones 2–5 Gate Review (Iteration 1)
| Agent | Role | Verdict | Source | Notes |
|-------|------|---------|--------|-------|
| reviewer_m2_m3_2 | teamwork_reviewer | REQUEST_CHANGES | handoff.md | 1. Hardcoded test fixture bypass `allow_identical_short_text` in `ContextBuilder` (`src/ragassist/modules/retrieval/application/__init__.py:51-53`).<br>2. Production worker (`src/ragassist/worker/main.py`) imports test fake `from fakes.documents import InMemoryDocumentRepository`.<br>3. `src/ragassist/modules/knowledge/api/router.py` saves to in-memory dict instead of PostgreSQL with RLS. |
| reviewer_m4_m5_2 | teamwork_reviewer | REQUEST_CHANGES | handoff.md | 1. `src/ragassist/modules/assistant/api/router.py` message endpoint uses simulated dummy generator `_generate_sse_events` that yields canned strings (`f"'{user_query}'. "` and `chunk-{conversation_id[:8]}`) instead of invoking real 11-node LangGraph StateGraph (`build_graph()`).<br>2. Action interrupt decisions do not resume LangGraph thread via `Command(resume=...)`.<br>3. `src/ragassist/container.py` lacks factories for graph and service injection.<br>4. Production worker imports test fakes. |
| challenger_sec_2 | teamwork_challenger | APPROVE | handoff.md | 18 adversarial stress tests passing (S3 tenant prefixing, upload compensation, worker queue isolation, SQL injection resilience, RLS transaction context, JWT tamper rejection, massive markdown tables). |
| challenger_agent_2 | teamwork_challenger | REQUEST_CHANGES | handoff.md | 1. Assistant message endpoint bypasses LangGraph StateGraph engine.<br>2. DEFECT-41: State leak in `account_agent_node.py` where process-global `_PENDING_TOOL_CALLS` leaks across turns if approval is abandoned.<br>3. DEFECT-39 / DEFECT-05: Missing RBAC enforcement on document uploads and mutating actions.<br>4. Test-coupled deduplication hack in `ContextBuilder`. |
| auditor_m2_m5_2 | teamwork_auditor | CLEAN | handoff.md | Authentic algorithms verified across parsers, 5-pass chunker, RRF k=60, reranker cascade, 11-node LangGraph cyclic graph, WHATWG SSE streaming, and OpenAPI 3.1.0 specification. 0 hardcoded test mocks, 0 mock imports in production code, 0 inward layering violations. |

Gate Result: **FAIL** (Reviewers & Challenger requested changes)

---

## Action Plan for Iteration 2 Remediation
1. **ContextBuilder Deduplication**:
   Remove `allow_identical_short_text` completely from `src/ragassist/modules/retrieval/application/__init__.py`. Deduplicate passages based strictly on `chunk_id` (or `(document_id, heading_path)`). Update `tests/unit/modules/retrieval/test_context_builder.py::TestBudget::test_a_large_budget_keeps_every_hit` to supply distinct chunks `f"short text {i}"` if needed.
2. **Plumb Real LangGraph StateGraph into Assistant API Router**:
   In `src/ragassist/modules/assistant/api/router.py`:
   - Replace `_generate_sse_events` dummy generator with real invocation of `build_graph()` or `compiled_graph.astream_events(...)`.
   - Map actual graph events into WHATWG SSE events (`token`, `citation`, `tool_call`, `interrupt`, `done`, `error`).
   - In `decide_action`: resume the interrupted LangGraph graph execution using the checkpointer and `Command(resume=...)`.
3. **Plumb Services in Container**:
   In `src/ragassist/container.py`:
   Provide dependency injection factories for `AssistantCompiledGraph`, `RetrievalService`, and `DecisionService` so routers can cleanly inject them.
4. **Remove Test Fake Imports from Production Worker**:
   In `src/ragassist/worker/main.py`:
   Remove `from fakes.documents import InMemoryDocumentRepository`. Wire a production document repository adapter (e.g. `PgDocumentRepository` or in-tree repository using `UnitOfWork` and `ChunkModel`).
5. **Fix DEFECT-41 (Pending Action State Leak)**:
   In `src/ragassist/modules/assistant/graph/nodes/account_agent_node.py`:
   Store pending action approvals inside `AssistantState` (which is persisted by the Postgres checkpointer) rather than process-global `_PENDING_TOOL_CALLS`, or clear stale pending calls when a new user turn begins.
6. **Enforce Admin RBAC (DEFECT-39 & DEFECT-05)**:
   In `src/ragassist/modules/knowledge/api/router.py`: require `UserRole.ADMIN` on `POST /v1/documents`.
   In `src/ragassist/modules/actions/application.py`: verify `principal.role == UserRole.ADMIN` on mutating tools.
