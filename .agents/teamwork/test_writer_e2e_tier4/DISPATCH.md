# DISPATCH — test_writer_e2e_tier4

- **Role**: E2E Test Writer (Tier 4: Production Surface, Streaming & Observability)
- **Working Directory**: d:\Coding\RagAssist-1
- **State Folder**: d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier4
- **Original Request**: d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md
- **Project Index**: d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md
- **Test Infra**: d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md

## Exclusive Write Ownership
You have exclusive write ownership over:
- `tests/e2e/test_tier4_production.py`
- `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier4\`

DO NOT modify files in `src/ragassist/` (source code is owned exclusively by builders).

## Task Instructions
1. Read `TEST_INFRA.md` § 2.1 (Tier 4 definition), § 3 (Features 28, 29, 30, 32, 33, 34).
2. Read `docs/api/sse-contract.md` to understand the SSE event format:
   - `event: token` with JSON `{text: "..."}`
   - `event: source` with JSON `{title: "...", page: 1, snippet: "..."}`
   - `event: action` with JSON `{tool: "...", status: "..."}`
   - `event: error` with JSON `{code: "...", message: "..."}`
   - `event: done` with JSON `{conversation_id: "...", message_id: "..."}`
3. Implement `tests/e2e/test_tier4_production.py` specifying opaque-box production surface tests for:
   - REST API Endpoints: Conversation thread creation (`POST /api/v1/conversations`), listing, and fetching message history.
   - SSE Streaming Contract: Verifying parsing of Server-Sent Events, sequential token delivery, citation event schema, action confirmation events, and clean termination with `done`.
   - Multipart Document Upload: File upload to `/api/v1/knowledge/upload`, streaming to S3, SQS job dispatch with 202 Accepted.
   - Prometheus Metrics: Scraping `/metrics` to verify presence of HTTP request counters, latency histograms, and RAG score metrics.
   - LangSmith Tracing Switch: Verification of tracing flag toggle behavior without error.
   - RAG Triad Evaluator: Contract testing for automated evaluation runner calculating faithfulness, answer relevance, and context precision metrics.
4. Execute test verification using `BypassSandbox=True`.
5. Write `handoff.md` in `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier4\`.
6. Send a message to orchestrator upon completion.


## 2026-11-08T09:08:42Z
You are test_writer_e2e_tier4 (E2E Test Writer for Tier 4: Production Surface, Streaming & Observability) for project RagAssist.

CRITICAL INSTRUCTIONS:
1. You MUST read the original user request at:
   `d:\Coding\RagAssist-1\.agents\teamwork\ORIGINAL_REQUEST.md`
   before beginning work.
2. Read `d:\Coding\RagAssist-1\.agents\teamwork\TEST_INFRA.md`, `d:\Coding\RagAssist-1\.agents\teamwork\PROJECT.md`, `docs/api/sse-contract.md`, and `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier4\DISPATCH.md`.
3. Check existing files in:
   - `tests/e2e/conftest.py`
   - `tests/e2e/test_tier1_features.py`
4. Your exclusive write ownership is:
   - `tests/e2e/test_tier4_production.py`
   DO NOT modify files in `src/` (implementation code is owned by builders).

5. Test Design Requirements for Tier 4 (`test_tier4_production.py`):
   - Design at least 25-30 rigorous opaque-box production surface tests covering:
     1. Conversation Lifecycle API (`/api/v1/conversations`):
        - Thread creation with tenant isolation.
        - Conversation listing with pagination.
        - Message retrieval.
     2. Server-Sent Events (SSE) Streaming Protocol (`docs/api/sse-contract.md`):
        - Parse SSE data chunks: `event: token`, `event: source`, `event: action`, `event: error`, `event: done`.
        - Verify token assembly produces complete coherent message.
        - Verify citation event JSON payloads contain title, page, snippet.
        - Verify graceful error reporting via SSE error event instead of abrupt connection drop.
     3. Document Ingestion Upload Endpoint (`/api/v1/knowledge/upload`):
        - Multipart file upload validation.
        - 202 Accepted response with upload task ID.
     4. Prometheus Observability (`/metrics`):
        - Verify Prometheus metric exposition.
     5. LangSmith Distributed Tracing:
        - Verify tracing flags and callback hooks.
     6. RAG Triad Benchmark Runner:
        - Contract testing for faithfulness, answer relevance, context precision scoring.
   - When running pytest commands on Windows, ALWAYS set `BypassSandbox=True`.

6. Deliverables:
   - Save your completed test file to `tests/e2e/test_tier4_production.py`.
   - Run the test suite and verify test execution.
   - Write your handoff report in `d:\Coding\RagAssist-1\.agents\teamwork\test_writer_e2e_tier4\handoff.md`.
   - Send completion message to orchestrator via `send_message`.
