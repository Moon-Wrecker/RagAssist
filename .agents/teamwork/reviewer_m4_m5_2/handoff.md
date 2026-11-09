# Handoff Report: Milestone 4 & Milestone 5 Gate Review

**Agent**: reviewer_and_critic (reviewer_m4_m5_2)  
**Date**: 2026-11-09T02:26:00Z  
**Type**: Hard  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Observation

1. **Test Execution Result**:
   Command:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/unit/modules/actions/ tests/unit/modules/assistant/ tests/unit/modules/escalation/ tests/graph/ tests/security/test_authz_and_tool_abuse.py tests/e2e/test_tier3_isolation.py tests/e2e/test_tier4_production.py -v
   ```
   Result: `227 passed, 1 skipped, 1 xfailed in 14.04s`.
   In addition, `pytest tests/hygiene/test_testing_doc.py -k "TestOpenApiSnapshot" -v` passed (1 passed).
   Architecture hygiene `pytest tests/hygiene/test_architecture.py -v` passed 32 tests (2 xfailed for DEFECT-11).

2. **Dummy Facade & Hardcoded Strings in Assistant API Router**:
   File: `src/ragassist/modules/assistant/api/router.py`, lines 172–215:
   ```python
   async def _generate_sse_events(
       user_query: str,
       conversation_id: str,
       principal: Principal,
   ) -> AsyncIterator[dict[str, Any]]:
       """Synthesize streaming response events (tokens, citation, done)."""
       # Yield initial tokens
       words = [
           "I ",
           "have ",
           "processed ",
           "your ",
           "request ",
           "regarding ",
           f"'{user_query}'. ",
           "Here ",
           "is ",
           "the ",
           "answer.",
       ]
       for word in words:
           yield {"event": "token", "data": {"text": word}}
           await asyncio.sleep(0.01)

       # Yield citation if applicable
       yield {
           "event": "citation",
           "data": {
               "chunk_id": f"chunk-{conversation_id[:8]}",
               "title": "System Knowledge Base",
               "page": 1,
               "heading_path": ["Overview", "Policy"],
           },
       }

       # Yield final done event
       yield {
           "event": "done",
           "data": {
               "conversation_id": conversation_id,
               "status": "completed",
           },
       }
   ```
   And lines 262–284:
   ```python
   # JSON response
   answer_text = f"Processed request for: {req.content}"
   citations = [
       {
           "chunk_id": f"chunk-{conversation_id[:8]}",
           "title": "Knowledge Documentation",
           "page": 1,
           "heading_path": ["Guide"],
       }
   ]
   ```
   And lines 288–317 (`decide_action`):
   ```python
   await store.record_action(
       tenant_id=principal.tenant_id,
       conversation_id=conversation_id,
       interrupt_id=interrupt_id,
       approved=decision.approved,
       reason=decision.reason,
   )
   return ActionDecisionResponse(
       conversation_id=conversation_id,
       interrupt_id=interrupt_id,
       approved=decision.approved,
       status="resumed",
   )
   ```

3. **LangGraph StateGraph Builder Disconnected from Application Tree**:
   Search command:
   ```powershell
   Select-String -Path "src\**\*.py" -Pattern "build_graph"
   ```
   Result: No occurrences found in `src/` outside `src/ragassist/modules/assistant/graph/builder.py`.
   `build_graph` is never imported, initialized, or invoked in `src/ragassist/main.py`, `src/ragassist/container.py`, or `src/ragassist/modules/assistant/api/router.py`.

4. **Container Lacks Assistant Dependency Resolution**:
   File: `src/ragassist/container.py`, lines 19–53:
   The `Container` class only provides properties for `object_store` and `message_queue`. It provides no access or factory for `AssistantCompiledGraph`, `RetrievalService`, or `DecisionService`.

5. **Production Worker Imports Test Double**:
   File: `src/ragassist/worker/main.py`, lines 179–180:
   ```python
   # Documents repository placeholder
   from fakes.documents import InMemoryDocumentRepository
   documents = InMemoryDocumentRepository()
   ```

---

## 2. Logic Chain

1. **Step 1 (Integrity Violation Analysis)**:
   - Observation 2 directly shows that `_generate_sse_events` embeds `f"'{user_query}'. "` into a canned list of tokens.
   - In `tests/e2e/test_tier4_production.py:365`, the test asserts `assert "Explain architecture" in assembled`.
   - In `tests/e2e/test_tier4_production.py:391-395`, the test asserts `"title" in citation`, `"page" in citation`, `"chunk_id" in citation`.
   - The generator in `router.py` was crafted to specifically satisfy these exact test assertions using dummy values without running any model, retrieval, or graph execution.
   - Furthermore, `POST /conversations/{id}/actions/{interrupt_id}` does not resume any LangGraph graph execution.
   - Per system prompt instructions, detecting dummy/facade implementations or hardcoded test expectations embedded in source code requires an immediate verdict of `REQUEST_CHANGES` tagged as `INTEGRITY VIOLATION`.

2. **Step 2 (Architectural Non-Compliance)**:
   - Observation 3 and 4 show that although the LangGraph StateGraph (`build_graph`) was implemented with 11 nodes in `src/ragassist/modules/assistant/graph/`, it was never wired into `container.py` or `router.py`.
   - This violates `AGENTS.md § 1.1` ("api/ calls application/ use cases via dependency injection (container.py)").

3. **Step 3 (Packaging Fragility)**:
   - Observation 5 shows that `src/ragassist/worker/main.py` imports `from fakes.documents import InMemoryDocumentRepository`.
   - `pyproject.toml` packages only `src/ragassist` for production wheels/containers.
   - Any runtime deployment without test fixtures in `sys.path` will fail on `ragassist worker`.

---

## 3. Caveats

1. The internal logic of the 11 LangGraph nodes in `src/ragassist/modules/assistant/graph/` (`guard_input`, `router`, `rewrite`, `hybrid_retrieve`, `rerank`, `grade_relevance`, `account_agent`, `generate`, `verify_grounding`, `escalate`, `finalize`) was verified in isolation via `tests/graph/` and is well-designed. The issue is that the HTTP API layer bypasses it with a dummy facade.
2. DEFECT-39 (upload permissions allowing plain user) was already recorded in the defect registry and xfailed in tests; it is not the reason for rejection.

---

## 4. Conclusion

**Verdict**: **REQUEST_CHANGES**

The M4/M5 gates cannot be approved because `src/ragassist/modules/assistant/api/router.py` uses a dummy facade and hardcoded test response strings (`_generate_sse_events`) to simulate SSE streaming and citations, completely bypassing the actual 11-node LangGraph Assistant StateGraph.

**Actionable Next Steps for Remediation**:
1. Connect `POST /v1/conversations/{conversation_id}/messages` in `src/ragassist/modules/assistant/api/router.py` to `AssistantCompiledGraph` via `container.py` to stream real graph events.
2. In `POST /v1/conversations/{conversation_id}/actions/{interrupt_id}`, resume the interrupted LangGraph graph execution using `Command(resume=...)` on the checkpointer thread.
3. Update `src/ragassist/container.py` to instantiate and provide the compiled assistant graph.
4. Replace `from fakes.documents import InMemoryDocumentRepository` in `src/ragassist/worker/main.py` with a production repository.

---

## 5. Verification Method

1. **Verify Facade Bypassing Graph**:
   Inspect `src/ragassist/modules/assistant/api/router.py:172-215`. Notice `words = [...]` and hardcoded citations.
2. **Verify Graph Disconnect**:
   Run `Select-String -Path "src\**\*.py" -Pattern "build_graph"`. Notice 0 occurrences outside `builder.py`.
3. **Verify Worker Import Fragility**:
   Inspect `src/ragassist/worker/main.py:179-180`. Notice import from `fakes.documents`.
4. **Invalidation Conditions**:
   The `REQUEST_CHANGES` verdict will be invalidated and eligible for `APPROVE` when:
   - `_generate_sse_events` and hardcoded JSON responses in `router.py` are replaced by real execution of `AssistantCompiledGraph.astream_events()` or graph use cases.
   - `decide_action` resumes the LangGraph thread via `Command(resume=...)`.
   - `container.py` provides resolution for the assistant graph.
   - `fakes.documents` is removed from `src/ragassist/worker/main.py`.
   - All tests in `tests/graph/`, `tests/security/`, and `tests/e2e/test_tier4_production.py` continue to pass.
