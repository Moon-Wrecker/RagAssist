# DISPATCH — worker_m4

- **Role**: Milestone 4 Implementer (Mock SaaS Actions, LangGraph Core & Escalation)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\worker_m4
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md

## Exclusive Write Ownership
You have exclusive write ownership over:
- `src/ragassist/modules/actions/` (Mock SaaS client and LangChain tools)
- `src/ragassist/modules/escalation/` (Human escalation service)
- `src/ragassist/modules/assistant/domain/` (State definitions, graph models)
- `src/ragassist/modules/assistant/graph/` (LangGraph state machine, nodes, conditional edges, checkpointer)
- `tests/unit/test_actions.py`
- `tests/graph/test_agent_workflow.py`

DO NOT modify files outside your write ownership (e.g., `platform/storage/`, `platform/queue/`, `modules/knowledge/`, `modules/retrieval/`, `src/ragassist/main.py`).

## Task Instructions
1. Implement Mock SaaS HTTP Client and LangChain Action Tools in `src/ragassist/modules/actions/`:
   - Async HTTP client connecting to `http://localhost:8001` (mock SaaS service).
   - Implement tools: `get_overview`, `get_subscription`, `get_invoices`, `update_billing_email`, and `create_ticket`.
   - Implement role-based action gating (e.g., `update_billing_email` requires admin role; read-only roles are prevented from mutating state).
2. Implement Human Escalation Service in `src/ragassist/modules/escalation/`:
   - Gated escalation triggered when routing confidence or chunk relevance < `ESCALATION_THRESHOLD` (0.65).
   - Creates support ticket with user context, question history, and reason.
3. Implement LangGraph Cyclical Workflow in `src/ragassist/modules/assistant/graph/`:
   - `AssistantState` with typed channels (`messages`, `query`, `route`, `retrieved_chunks`, `graded_chunks`, `action_result`, `grounding_verdict`, `escalated`, `loop_count`).
   - Implement 8 graph nodes:
     1. `guardrail`: System One input safety check (blocks injection/attacks).
     2. `route`: Routes query (`rag_search`, `saas_action`, `general_chat`, `human_escalation`).
     3. `retrieve`: Calls hybrid retrieval service.
     4. `grade`: System One chunk relevance grading (filters out irrelevant chunks; rewrites query if all irrelevant).
     5. `generate`: Synthesizes grounded answer using primary LLM with citation tags `[1]`.
     6. `rewrite`: Reformulates search query if retrieved chunks fail relevance threshold (loop bound: max 2 rewrites).
     7. `action`: Executes Mock SaaS action tools with permission checks and human-in-the-loop interrupt if confirmation is required.
     8. `escalate`: Creates support ticket when confidence/relevance < 0.65.
   - Assemble citations with source document title, page numbers, and breadcrumbs.
   - Checkpointer: Integrate PostgreSQL state checkpointer with `{tenant_id}:{conversation_id}` thread namespacing.
4. Write unit and graph tests in `tests/unit/test_actions.py` and `tests/graph/test_agent_workflow.py`. Use `BypassSandbox=True` when invoking pytest on Windows.
5. Write `changes.md` and `handoff.md` in `d:\Coding\RagAssist-1\.agents\teamwork\worker_m4\`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.


## 2026-11-08T09:04:42Z
Received dispatch from parent (be9621e6-d3bc-446a-abb9-2d0c46239ab1):
Milestone 4 Implementer: Mock SaaS Actions, LangGraph Core & Escalation for project RagAssist.
Exclusive write ownership:
- `src/ragassist/modules/actions/`
- `src/ragassist/modules/escalation/`
- `src/ragassist/modules/assistant/domain/`
- `src/ragassist/modules/assistant/graph/`
- `tests/unit/test_actions.py`
- `tests/graph/test_agent_workflow.py`
Deliverables:
- `changes.md`
- `handoff.md`
- Send completion message to orchestrator via `send_message`.
