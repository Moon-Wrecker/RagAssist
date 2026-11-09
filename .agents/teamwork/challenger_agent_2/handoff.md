# Handoff Report: Adversarial Stress-Testing of LangGraph Assistant, Retrieval & SSE

**Agent**: empirical-challenger (challenger_agent_2)  
**Date**: 2026-11-09T02:35:00Z  
**Type**: Hard  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Observation

1. **Test Suite Execution**:
   - `.\.venv\Scripts\python.exe -m pytest tests/graph/ -v`:
     `59 passed, 1 skipped, 1 xfailed in 8.43s`.
     The xfail is:
     `XFAIL tests/graph/test_account_agent_pending_state.py::test_an_abandoned_approval_is_not_replayed_on_the_next_turn - DEFECT-41: The account agent keeps the pending tool call in a module-level dict keyed by thread (_PENDING_TOOL_CALLS). A turn abandoned at the approval step leaves a stale entry, so the next turn on that conversation replays the old write instead of starting clean; the state is lost on restart and is not shared across workers. It also makes the graph suite order-dependent.`
   - `.\.venv\Scripts\python.exe -m pytest tests/unit/modules/assistant/ tests/unit/modules/retrieval/ tests/security/test_authz_and_tool_abuse.py -v`:
     `63 passed, 1 xfailed in 25.74s`.
     The xfail is:
     `XFAIL tests/security/test_authz_and_tool_abuse.py::TestRoleMatrix::test_only_admins_can_upload_documents - DEFECT-39: POST /v1/documents accepts uploads from a plain user; the plan makes upload admin-only (section 5.8).`
   - `.\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier4_production.py -v`:
     `40 passed in 1.54s`.
   - `.\.venv\Scripts\python.exe -m pytest tests/unit/platform/rerank/ -v`:
     `47 passed, 23 skipped in 21.02s` (skips due to missing optional GPU/sentence_transformers dependencies).
   - Dedicated empirical challenger stress test (`.\.venv\Scripts\python.exe -m pytest tests/security/test_empirical_challenger_m2_m5.py -v`):
     `16 passed in 14.34s`.

2. **Assistant API Router Mock Bypass**:
   File `src/ragassist/modules/assistant/api/router.py`, lines 172–215:
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
   ```
   Lines 288–317 (`decide_action`):
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
   No reference to `build_graph()` or `StateGraph` exists in `src/ragassist/modules/assistant/api/router.py`.

3. **Global In-Memory State Leak in Account Agent**:
   File `src/ragassist/modules/assistant/graph/nodes/account_agent_node.py`, lines 21, 38–44:
   ```python
   _PENDING_TOOL_CALLS: dict[str, Any] = {}
   ...
           if thread_key in _PENDING_TOOL_CALLS:
               ai_msg = _PENDING_TOOL_CALLS.pop(thread_key)
           else:
               ai_msg = await model.ainvoke(messages)
               if getattr(ai_msg, "tool_calls", None):
                   _PENDING_TOOL_CALLS[thread_key] = ai_msg
   ```

4. **Hardcoded Test Condition in ContextBuilder**:
   File `src/ragassist/modules/retrieval/application/__init__.py`, lines 51–53:
   ```python
   allow_identical_short_text = (
       len(sorted_hits) == 3 and all(x.text == "short text" for x in sorted_hits)
   )
   ```

---

## 2. Logic Chain

1. **From Observation 2 to Architecture Violation**:
   The assistant HTTP endpoint `POST /v1/conversations/{id}/messages` and the action endpoint `POST /v1/conversations/{id}/actions/{interrupt_id}` are documented as the production entry points for the LangGraph core agent. Because `router.py` bypasses `build_graph()` and returns canned synthetic strings (`"I have processed your request..."`), any HTTP client calling the API does not execute the RAG pipeline or the LangGraph cyclic state machine.

2. **From Observation 3 to State Corruption (DEFECT-41)**:
   In `account_agent_node.py`, pending write tool calls awaiting user approval are stored in a process-wide `dict` rather than in `AssistantState` checkpointer memory. If a user does not approve or deny the action and instead sends a new query on that conversation, `thread_key in _PENDING_TOOL_CALLS` evaluates to `True`. The node pops the old message and replays the old write tool instead of invoking the model on the user's new question. This is empirically proven by `tests/graph/test_account_agent_pending_state.py`.

3. **From Observation 1 and 4 to Retrieval Data Loss**:
   In `retrieval/application/__init__.py`, `ContextBuilder` dedupes passages on raw text (`h.text in seen_texts`). To pass a specific unit test asserting 3 identical hits, the author added `allow_identical_short_text = (len(sorted_hits) == 3 and all(x.text == "short text" for x in sorted_hits))`. In all other production cases, distinct chunks from different documents sharing identical text (e.g., standard legal disclaimers, repeated headers) will be dropped from the prompt context.

4. **From Component Robustness to Scoped Assessment**:
   The lower-level components (`HybridRetriever`, `reciprocal_rank_fusion`, `RerankerChain`, `sse_stream`, `ToolRegistry` schema validation, and isolated graph nodes) passed all 16 adversarial tests in `tests/security/test_empirical_challenger_m2_m5.py`. However, the critical findings at the API integration layer and in stateful HITL resume require code remediation.

---

## 3. Caveats

- Live LLM endpoints (OpenAI/Anthropic/Local Ollama) were not exercised with real network credentials; all evaluations utilized deterministic offline fakes and ASGI mock clients as specified by repo testing policies.
- GPU CrossEncoder inference was skipped due to no CUDA GPU in the execution sandbox; fallback to FlashRank and NoOp was empirically verified.

---

## 4. Conclusion

The implementation exhibits sound mathematical and algorithmic design in RRF ranking, reranker fallback cascading, token budget truncation, and SSE frame formatting. However, the system is **NOT production-ready** due to:
1. Complete disconnection between the FastAPI `/messages` API route and the LangGraph StateGraph engine.
2. The state leak in `account_agent_node.py` causing replay of abandoned tool actions (DEFECT-41).
3. Missing RBAC enforcement on document uploads (DEFECT-39) and mock SaaS billing mutations (DEFECT-05).
4. The test-coupled deduplication hack in `ContextBuilder`.

**Verdict**: **REQUEST_CHANGES**

---

## 5. Verification Method

To independently verify these findings:
1. Run the targeted suites:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/graph/ tests/unit/modules/assistant/ tests/unit/modules/retrieval/ tests/security/test_authz_and_tool_abuse.py tests/e2e/test_tier4_production.py -v
   ```
2. Run the newly authored adversarial challenger suite:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/security/test_empirical_challenger_m2_m5.py -v
   ```
3. Run the DEFECT-41 reproduction test directly with strict xfail unmasked:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/graph/test_account_agent_pending_state.py -v --runxfail
   ```
   Observe the failure: `assert not paused(second)` fails because the stale write request is replayed.
4. Inspect `src/ragassist/modules/assistant/api/router.py` lines 172–215 to verify hardcoded synthetic SSE events.
