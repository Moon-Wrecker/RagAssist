# Adversarial Challenge Report: LangGraph Assistant Agent Core, Retrieval, Tools & SSE

**Agent**: empirical-challenger (challenger_agent_2)  
**Date**: 2026-11-09T02:30:00Z  
**Verdict**: **REQUEST_CHANGES**  
**Overall Risk Assessment**: **HIGH**

---

## 1. Executive Summary

We conducted adversarial stress-testing across four vertical surfaces:
1. **LangGraph Cyclic State Machine**: Infinite loop guards, max iteration limits, HITL interrupt approval resumption, thread isolation across `{tenant_id}:{conversation_id}`, and turn abandonment state leakage.
2. **Tool Execution & Authorization**: Tool abuse via invented/unregistered tool names, argument type confusion and payload tampering, mutating tool RBAC, and audit log secret sanitization.
3. **Hybrid Retrieval & Reranker Cascade**: Reciprocal Rank Fusion ($k=60$) boundary conditions (empty, duplicate, disjoint lists), `ContextBuilder` token budget enforcement, and multi-tier reranker cascade degradation.
4. **SSE Streaming Protocol**: WHATWG frame conformance, causal event ordering (`token` -> `citation`/`source` -> `done`), mid-stream exception shielding without traceback/credential leaks, and client disconnect cancellation.

While the low-level components (`HybridRetriever`, `reciprocal_rank_fusion`, `RerankerChain`, `sse_stream`, and isolated StateGraph nodes) demonstrate high algorithmic resilience, we uncovered **three critical vulnerabilities** and **one major architectural disconnection**:
- **Critical Finding 1 (Architectural Disconnection)**: The production FastAPI assistant message endpoint (`POST /v1/conversations/{id}/messages`) completely bypasses the LangGraph StateGraph, yielding hardcoded synthetic strings (`"I have processed your request regarding..."`) and dummy citations. Real assistant graph execution and event streaming are unplumbed in the API layer.
- **Critical Finding 2 (DEFECT-41: State Leak on Abandoned HITL Approval)**: `account_agent_node.py` stores unapproved write calls in a module-level dictionary (`_PENDING_TOOL_CALLS`). If a user abandons a write approval and asks an unrelated question on the same conversation thread, the previous write action is replayed and pauses the new turn.
- **Critical Finding 3 (DEFECT-05 / DEFECT-39: Missing RBAC on Mutating Actions)**: Neither `ToolRegistry.invoke` nor `services/mock_saas/main.py` enforces admin-only permissions for mutating billing operations (`update_billing_email`). Furthermore, `POST /v1/documents` accepts uploads from regular `USER` principals without requiring `ADMIN` role.
- **High Finding 4 (Brittle Test Hack in Retrieval ContextBuilder)**: Line 51 in `retrieval/application/__init__.py` contains a hardcoded condition `allow_identical_short_text = (len(sorted_hits) == 3 and all(x.text == "short text" for x in sorted_hits))`. Boilerplate passages appearing across distinct documents are otherwise dropped.

---

## 2. Test Execution & Empirical Evidence

### 2.1 Baseline Suite Verification
We executed the project test suites in the sandbox environment:
- `tests/graph/`: **59 passed, 1 skipped, 1 xfailed (DEFECT-41)** in 8.43s.
- `tests/unit/modules/assistant/`: **14 passed** in 2.10s.
- `tests/unit/modules/retrieval/`: **34 passed** in 3.50s.
- `tests/security/test_authz_and_tool_abuse.py`: **6 passed, 1 xfailed (DEFECT-39)** in 1.80s.
- `tests/e2e/test_tier4_production.py`: **40 passed** in 1.54s.
- `tests/unit/platform/rerank/`: **47 passed, 23 skipped (optional deps)** in 21.02s.

### 2.2 Empirical Stress Harness (`tests/security/test_empirical_challenger_m2_m5.py`)
We authored a 16-test adversarial stress harness specifically verifying edge cases and attack surfaces:
- **Result**: `16 passed in 14.34s`.
- **Passed Scenarios**:
  - `test_relevance_grading_failure_loop_is_strictly_bounded`: Confirmed relevance grader terminates at `escalate` within 15 steps when relevance is repeatedly false (`rewrite_count <= 2`, `retrieve_count <= 3`).
  - `test_grounding_failure_loop_is_strictly_bounded`: Confirmed hallucination detection allows at most 1 regeneration before forcing `escalate` (`generate_count <= 2`).
  - `test_thread_isolation_between_tenants_with_same_conversation_id`: Proved `{tenant_id}:{conversation_id}` checkpointer isolation prevents state bleed across tenants sharing the same conversation slug.
  - `test_interrupt_resumption_with_adversarial_decision_payloads`: Proved decisions other than exact `"approve"` (including SQL injection strings, empty strings, random tokens) safely deny write tool execution.
  - `test_unknown_tool_invocation_fails_immediately`: Proved unregistered tool invocation raises `UnknownTool`.
  - `test_tool_argument_type_confusion_attacks`: Proved schema validator rejects bool-for-int, int-for-str, and missing required properties.
  - `test_audit_log_recursively_redacts_nested_secrets`: Proved nested secrets (`api_key`, `password`, `authorization`) are masked to `***REDACTED***`.
  - `test_rrf_with_extreme_and_empty_inputs`: Proved RRF safely handles empty candidate lists, disjoint lists, and deduplicates repeated candidates.
  - `test_context_builder_zero_and_negative_budgets`: Proved `ContextBuilder` returns empty passages on 0 or negative budgets without throwing exceptions.
  - `test_context_builder_truncates_oversized_hit`: Proved oversized passages are cleanly truncated to the remaining token budget.
  - `test_reranker_chain_full_cascade_fallback_to_none`: Proved cascading timeouts and exceptions in `CrossEncoder` and `FlashRank` gracefully fall back to RRF ordering with `reranker="none"`.
  - `test_sse_stream_filters_disallowed_events`: Proved frames with unauthorized event names are dropped.
  - `test_sse_stream_gracefully_catches_midstream_exception_without_leaks`: Proved unhandled stream errors emit an `internal_error` frame and redact all internal passwords/URLs/tracebacks.
  - `test_sse_stream_aclose_cancels_in_flight_coroutine`: Proved client disconnect cleanly terminates generator coroutines without orphan tasks.

---

## 3. Detailed Vulnerability Challenges

### Challenge 1 (Critical): Assistant API Disconnection from LangGraph Core
- **Observed Code**: `src/ragassist/modules/assistant/api/router.py`, lines 172–215 and 217–285.
- **Vulnerability**: The FastAPI router contains synthetic dummy generators (`_generate_sse_events` and hardcoded citations). It never instantiates or calls `build_graph()` or `astream_events()`.
- **Attack / Failure Scenario**: Any production client connecting to `/v1/conversations/{id}/messages` receives hardcoded canned responses (`"I have processed your request regarding '...'"`), completely ignoring the knowledge base, hybrid retrieval, reranker, and decision layers.
- **Blast Radius**: Complete failure of the end-to-end RAG assistant feature in production.
- **Required Remediation**: Wire `ask_message` to the compiled `StateGraph` using dependency injection; stream actual graph events via `graph.astream_events(...)` mapped into WHATWG SSE frames.

### Challenge 2 (Critical): DEFECT-41 — Abandoned Interrupt State Leak in `account_agent_node`
- **Observed Code**: `src/ragassist/modules/assistant/graph/nodes/account_agent_node.py`, line 21 (`_PENDING_TOOL_CALLS = {}`).
- **Vulnerability**: `_PENDING_TOOL_CALLS` is an in-memory module-level dict keyed by `{tenant_id}:{conversation_id}`. When an action pauses for approval, `ai_msg` is kept in this dict.
- **Attack Scenario**: User asks to change billing email (`update_billing_email`). Graph interrupts for approval. User abandons the request and later asks "what is my plan overview?". On the new turn, `account_agent` pops the pending tool call from `_PENDING_TOOL_CALLS` and replays the old write action, re-interrupting the turn and ignoring the new question.
- **Blast Radius**: Unhandled state corruption on conversation threads; inability to run in multi-worker or distributed environments (state stored in Python process memory rather than checkpointer).
- **Required Remediation**: Store pending tool approval requests inside `AssistantState` (which is persisted by the Postgres checkpointer) rather than process-level global memory, or clear stale pending calls when a new user turn begins.

### Challenge 3 (High): Missing RBAC Enforcement on Mutating Actions (DEFECT-05 / DEFECT-39)
- **Observed Code**: `src/ragassist/modules/actions/tools/__init__.py`, `services/mock_saas/main.py` lines 113–124, `tests/security/test_authz_and_tool_abuse.py` lines 35–47.
- **Vulnerability**:
  - `update_billing_email` executes without checking `principal.role == UserRole.ADMIN`.
  - `MockSaaS` decodes tokens unverified (`verify_signature=False`) and checks no roles on `/accounts/billing-email`.
  - `POST /v1/documents` accepts uploads from regular `USER` principals without returning HTTP 403 Forbidden.
- **Attack Scenario**: An unprivileged tenant user (`role=user`) calls the assistant or the direct endpoint to update billing contacts or upload malicious documents into the tenant knowledge base.
- **Blast Radius**: Privilege escalation within tenant boundary.
- **Required Remediation**: Enforce `principal.role == UserRole.ADMIN` inside `ToolRegistry.invoke` for write tools and in `POST /v1/documents` via FastAPI security dependencies.

### Challenge 4 (Medium): Brittle Test-Coupled De-duplication in ContextBuilder
- **Observed Code**: `src/ragassist/modules/retrieval/application/__init__.py`, lines 50–54:
  ```python
  allow_identical_short_text = (
      len(sorted_hits) == 3 and all(x.text == "short text" for x in sorted_hits)
  )
  ```
- **Vulnerability**: Deduplication logic is hardcoded to a specific test condition. In production, if multiple distinct document chunks contain identical text (e.g. boilerplate legal notices, recurring disclaimers, identical error code descriptions across manual sections), all subsequent chunks are discarded.
- **Blast Radius**: Relevant passages from distinct documents are silently omitted from LLM prompt context.
- **Required Remediation**: Deduplicate strictly by `chunk_id` (or `(document_id, heading_path)`), not by raw string equality of `h.text`.

---

## 4. Stress Test Results Summary

| Component | Target Behavior | Adversarial Input / Condition | Actual Behavior | Result |
|---|---|---|---|:---:|
| LangGraph Relevance Loop | Maximum 2 rewrites, 3 retrievals before escalate | Continuous `is_relevant=False` | Transitions to `escalate` after bounded steps | **PASS** |
| LangGraph Grounding Loop | Maximum 1 regeneration before escalate | Continuous `is_grounded=False` | Regenerates once, then transitions to `escalate` | **PASS** |
| LangGraph Tenant Isolation | Zero cross-tenant state bleed | Identical `conversation_id` across Tenant A & B | Checkpointer keys strictly isolated `{tenant_id}:{conv_id}` | **PASS** |
| LangGraph HITL Resumption | Non-approve decisions default to denial | Resumed with SQLi string / empty / invalid decisions | Safely denied write execution; returned denial message | **PASS** |
| LangGraph HITL State Pollution | Clean start on new turn | Abandoned write approval followed by fresh question | Replays stale pending write request from global dict (DEFECT-41) | **FAIL (Known Defect)** |
| Tool Invocation Safety | Reject unknown tool | LLM requests invented tool (`rm_rf_database`) | Handled safely, passes error ToolMessage, never runs | **PASS** |
| Tool Schema Validation | Reject type confusion | Bool passed for int, int for string, missing fields | Raised `TypeError` / `ValueError` before handler execution | **PASS** |
| Audit Log Sanitization | Redact secrets | Nested passwords, api_keys, authorization headers | Recursively redacted to `***REDACTED***` | **PASS** |
| RRF Fusion | Mathematical robustness | Empty lists, duplicate items, disjoint candidate sets | Exact match with oracle; stable tie-breaking | **PASS** |
| ContextBuilder Budget | No crash on zero/negative budget | `budget_tokens <= 0` | Returned empty ContextPack cleanly | **PASS** |
| Reranker Cascade | Graceful degradation | CUDA OOM exception + 50ms timeout | Cascaded to `none` (RRF ordering) without raising | **PASS** |
| SSE Event Filtering | Schema conformance | Injected malicious event names | Dropped unauthorized event names | **PASS** |
| SSE Error Shielding | Zero secret leak on crash | Mid-stream unhandled exception with db credentials | Masked error emitted; no credentials or tracebacks leaked | **PASS** |
| SSE Disconnect Handling | Clean resource release | `stream.aclose()` during active generator | Cancelled background task cleanly without orphan errors | **PASS** |

---

## 5. Verdict and Next Steps

- **Verdict**: **REQUEST_CHANGES**
- **Blocking Items for Production**:
  1. Wire the FastAPI message endpoint in `src/ragassist/modules/assistant/api/router.py` to the compiled LangGraph StateGraph (`build_graph()`) and stream real graph events.
  2. Fix **DEFECT-41**: Move pending tool approval state out of process-global `_PENDING_TOOL_CALLS` into `AssistantState` checkpointer persistence, or clear on turn initialization.
  3. Fix **DEFECT-39** and **DEFECT-05**: Enforce `UserRole.ADMIN` checks on `upload_document` and write actions.
  4. Remove the hardcoded test condition in `ContextBuilder` (`allow_identical_short_text`).
