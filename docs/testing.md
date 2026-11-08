# RagAssist test suite

This is the test suite for RagAssist. It was written before the implementation was finished, so it
states what the product must do, and it tells the implementation team exactly what is missing.

## Status at a glance

* **Runs today:** the shared kernel, the LLM and embedding adapters, the decision layer, the mock SaaS
  and identity endpoints, the hygiene rules, the self-checks that prove the fakes and oracles are
  right, and the security checks that do not need the assistant.
* **PENDING:** suites for code that is not written yet (ingestion, retrieval, reranking, the LangGraph
  assistant, the SSE contract, actions and escalation). They skip with a reason and are listed in
  `reports/pending.md`, so nothing is silently missing.
* **DEFECT:** known bugs in the current code. Each has a test that states the specified behaviour
  and is marked as an expected failure (strict). See `reports/defects.md`.

## Quick start

Run everything that does not need Docker or a live model:

```bash
pytest                         # all tiers except live (live is opt-in)
pytest tests/unit -p randomly  # random order: every suite must pass in any order
pytest -m pending -rs          # why each suite is still skipped
pytest -m defect --runxfail    # every open defect, failing as the spec requires
```

Windows (Git Bash or PowerShell) needs `;` between `PYTHONPATH` entries, for example
`PYTHONPATH="src;tests"`. The project venv is managed by uv:
`uv pip install --python .venv/Scripts/python.exe -e ".[dev]"`.

## Tiers and markers

Tiers come from the folder a test lives in; markers are applied automatically.

| Marker | Where | Needs |
|---|---|---|
| `unit` | `tests/unit` | nothing: fakes only, no network (enforced) |
| `graph` | `tests/graph` | nothing: LangGraph with scripted fakes |
| `security` | `tests/security` | nothing: mock SaaS over ASGI, rules decider |
| `integration` | `tests/integration` | Docker, or `TEST_DATABASE_ADMIN_URL` (see below) |
| `e2e` | `tests/e2e` | nothing; legacy tier being replaced (see the debt list) |
| `hygiene` | `tests/hygiene` | nothing: AGENTS.md rules and quality gates as tests |
| `selfcheck` | `tests/selfcheck` | nothing: proves fakes and oracles match their contracts |
| `eval` | `tests/unit/evals` | nothing: metric maths against oracles |
| `live` | `tests/live` | a real model endpoint and `--run-live` (or `RAGASSIST_LIVE=1`) |
| `gpu` | `tests/unit/platform/rerank/test_gpu_cross_encoder.py` | a CUDA GPU; skipped otherwise |
| `slow` | property-based suites | nothing; excluded from the quick loop |
| `defect` | any test asserting a known bug | nothing; strict xfail referencing `DEFECT-nn` |
| `network` | opt-out of the external-network guard | real internet access |
| `pending` | any suite for code not written yet | nothing; it skips with a `PENDING:` reason |

## Pending and drift

A planned symbol is resolved through `tests/support/specs/map.py`. There are three outcomes:

* **Found:** the test runs.
* **PENDING:** the module, or a package above it, does not exist yet, or it needs an optional
  dependency that is not installed. The test is skipped, with a reason beginning `PENDING:`. A module
  that exists but is still an empty stub is also PENDING.
* **DRIFT:** the module exists and defines other public names, but not the planned one. The test is
  skipped locally. In CI, `RAGASSIST_STRICT_PENDING=1` turns DRIFT into a failure, so a renamed class
  cannot hide behind a skip.

The fix for DRIFT is one of two small edits: rename the symbol in `map.py`, or change the call in the
test. The appendix below is the interface the tests assume, so it is also the implementation team's
checklist.

## Defects

Known bugs live in `tests/support/defects.py`. A test that asserts the specified behaviour and fails
against today's code is marked `@defect("DEFECT-nn")`, which is a strict xfail:

* while the bug exists, the test is an expected failure and the run stays green;
* when the bug is fixed, the test passes, which is reported as XPASS and fails the run;
* at that point, delete the marker and the registry entry. Fixed behaviour keeps a passing regression
  test (for example DEFECT-14 and DEFECT-20 were removed this way).

Every registered defect must be asserted by at least one test (`tests/hygiene/test_defect_registry.py`).

## Contracts and fakes

Each port has one contract suite in `tests/support/contracts`. A contract is written once, and each
adapter gets a subclass that supplies its fixture. Adding an adapter means writing a few lines, not new
tests. Fakes are checked against the same contracts in `tests/selfcheck`, so a fake cannot drift from
the port it imitates. `tests/selfcheck/test_contract_teeth.py` proves each contract rejects broken
implementations.

Fakes live in `tests/fakes`: scripted chat models, a scripted decider, an in-memory object store,
queue, retriever, reranker, document repository, tool registry, audit store and conversation store,
plus a controllable clock.

## Quality gates

| Gate | Command | Enforced in CI |
|---|---|---|
| Coverage: hard minimums per package and overall, plus a ratchet | `pytest ... --cov=src/ragassist --cov-branch --cov-report=json:coverage.json`, then `python tests/gates/check_coverage.py --report coverage.json` | yes (`coverage` job) |
| Ratchet update after coverage rises | `python tests/gates/check_coverage.py --report coverage.json --update-baseline` | manual |
| Random-order flake check (10 seeds) | `bash scripts/flake_check.sh 10` | nightly (`flake-nightly` job) |
| Cross-tenant leak gate (target 0) | `pytest tests/security/test_leak_gate.py` (report: `reports/leak_gate.json`) | yes |
| Prompt-injection floors and false positives | `pytest tests/security/test_injection_corpus.py` (report: `reports/injection.json`) | yes |
| Layering rules (AGENTS.md section 1) | `pytest tests/hygiene/test_architecture.py` | yes |
| No tautological tests | `pytest tests/hygiene/test_no_tautological_tests.py` | yes |

Coverage targets follow the plan: shared 95%, platform 90%, modules 90%, overall 85%. A group with no
code yet is reported as pending and never fails the gate. The baseline in
`tests/gates/coverage_baseline.json` can only move up.

## Live tier

Live tests call a real model and are never part of the default run. Configure them with environment
variables only; never write a key into a file.

```bash
RAGASSIST_LIVE_MODEL=gemma4:31b-cloud pytest tests/live --run-live          # local Ollama
RAGASSIST_LIVE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai \
RAGASSIST_LIVE_MODEL=gemini-flash-latest RAGASSIST_LIVE_API_KEY=... pytest tests/live --run-live
```

The endpoint is probed once per session. An unreachable endpoint or a missing model skips the tier
with a reason.

## Integration tier

Integration tests run against real PostgreSQL (pgvector) and LocalStack.

* **In CI:** a Postgres service container, with `TEST_DATABASE_ADMIN_URL` pointing at it.
* **On a laptop:** if `TEST_DATABASE_ADMIN_URL` is not set, a throwaway pgvector container is started
  with testcontainers (Docker must be running).
* **Safety:** these tests wipe the database they use. A database whose name does not contain `test`
  is refused, so the development database cannot be wiped by accident. Set
  `RAGASSIST_TEST_DB_ALLOW_WIPE=1` to override deliberately.

Row-level security is checked for every tenant table, once with the policies the architecture
specifies and once as shipped. The second run is the DEFECT-09 expected failure.

## Troubleshooting (Windows)

* `ModuleNotFoundError: ragassist`: set `PYTHONPATH="src;tests"` (semicolon, not colon).
* Docker-backed tests skip with "Docker is not available": start Docker Desktop, or set
  `TEST_DATABASE_ADMIN_URL`.
* A shell script failing on `\r` in its shebang has CRLF line endings. `test_repo_files.py` catches
  this; convert the file to LF.
* Testcontainers' reaper is disabled for this suite (`TESTCONTAINERS_RYUK_DISABLED=true`) because the
  reaper image is unreliable on Windows; containers are still stopped at the end of each session.
* A run that pauses for minutes often means the laptop slept. Re-run; the timing is not a test failure.

## Baseline

The numbers from the most recent full run are recorded below. They are a snapshot, not a target: the
gates and the pending report are the live measure.

<!-- baseline:begin -->
Full random-order run on 2026-11-09 (`pytest tests -p randomly --randomly-seed=1038592770`, local Windows,
Docker available): **1903 passed, 0 failed, 75 skipped, 70 expected failures (strict xfail)**.

* The 75 skips are PENDING modules and tiers that need an optional dependency or an opt-in marker (live LLM, GPU).
* The 70 expected failures are registered implementation defects (`reports/defects.md`); each flips to a hard
  failure the moment the builders fix it, so the registry entry and the `@defect` mark must be removed together.
<!-- baseline:end -->

## Interface the tests assume (generated)

This appendix is generated from `tests/support/specs/map.py`. The hygiene test
`tests/hygiene/test_testing_doc.py` fails if it drifts from the map. Regenerate it with:

```bash
python -c "import sys; sys.path[:0]=['src','.','tests']; from support.specs.map import render_appendix; print(render_appendix())"
```

<!-- appendix:begin (generated by support.specs.map.render_appendix; do not edit) -->
### actions

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `actions.ToolSpec` | `ragassist.modules.actions.application` | `ToolSpec` | ToolSpec(name, description, input_schema: dict, is_write: bool, handler); handler(principal, arguments) is async |
| `actions.ToolRegistry` | `ragassist.modules.actions.application` | `ToolRegistry` | ToolRegistry(tools); schemas() -> list[dict]; async invoke(name, arguments, principal) -> Any; validates arguments against input_schema before the handler runs; the tenant and user always come from the principal, never from arguments; raises UnknownTool |
| `actions.UnknownTool` | `ragassist.modules.actions.application` | `UnknownTool` | DomainError subclass |
| `actions.default_tools` | `ragassist.modules.actions.tools` | `default_tools` | default_tools(saas: SaaSClient) -> list[ToolSpec]: the production tool set |
| `actions.ApprovalPolicy` | `ragassist.modules.actions.application` | `ApprovalPolicy` | ApprovalPolicy(intent_check=None); requires_approval(tool) -> bool: writes always True, reads always False; intent_check never replaces approval |
| `actions.AuditLog` | `ragassist.modules.actions.application` | `AuditLog` | AuditLog(store); async record(principal, tool, arguments, *, approved, outcome, uow) -> entry (secrets masked); list_for_tenant(tenant_id) -> list |
| `actions.SaaSClient` | `ragassist.modules.actions.adapters.saas_client` | `SaaSClient` | SaaSClient(http: httpx.AsyncClient, max_retries=2, backoff_seconds=0.0, sleep=None); async get_overview, get_subscription, get_invoices, update_billing_email(email), create_ticket(payload) all take principal first; forwards principal.raw_token as a Bearer token; GET retried on 5xx, POST not |
| `actions.SaaSClientError` | `ragassist.modules.actions.adapters.saas_client` | `SaaSClientError` | .status_code; 4xx responses |
| `actions.SaaSUnavailable` | `ragassist.modules.actions.adapters.saas_client` | `SaaSUnavailable` | 5xx after retries |
| `actions.SaaSTimeout` | `ragassist.modules.actions.adapters.saas_client` | `SaaSTimeout` | transport timeout |
| `actions.SaaSResponseInvalid` | `ragassist.modules.actions.adapters.saas_client` | `SaaSResponseInvalid` | 2xx body fails the schema |

### assistant

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `assistant.build_graph` | `ragassist.modules.assistant.graph.builder` | `build_graph` | build_graph(*, settings, decision_service, generator_tiers: Mapping[str, BaseChatModel], retriever, reranker, tools, checkpointer) -> compiled LangGraph. Node names are the plan's: guard_input, router, rewrite, hybrid_retrieve, rerank, grade_relevance, account_agent, generate, verify_grounding, escalate, finalize. Final state keys: answer, route, citations, escalated, status, model_used, decider_used, complexity, tool_calls |
| `assistant.NODE_NAMES` | `ragassist.modules.assistant.graph.builder` | `NODE_NAMES` | tuple of every node name in the graph |
| `assistant.namespaced_thread_id` | `ragassist.modules.assistant.application.thread_guard` | `namespaced_thread_id` | namespaced_thread_id(tenant_id, conversation_id) -> '<tenant_id>:<conversation_id>' |
| `assistant.ensure_thread_access` | `ragassist.modules.assistant.application.thread_guard` | `ensure_thread_access` | async ensure_thread_access(principal, conversation_id, conversations) -> None; raises ThreadAccessDenied before any checkpoint read |
| `assistant.ThreadAccessDenied` | `ragassist.modules.assistant.application.thread_guard` | `ThreadAccessDenied` | DomainError subclass |
| `assistant.sse_stream` | `ragassist.modules.assistant.api.sse` | `sse_stream` | sse_stream(events: AsyncIterator[dict], *, heartbeat_seconds) -> AsyncIterator[str]: yields SSE frames (event:/data:/id: lines); a ': ping' comment when idle for heartbeat_seconds; closing the output closes the source |
| `assistant.SSE_HEADERS` | `ragassist.modules.assistant.api.sse` | `SSE_HEADERS` | dict with Content-Type text/event-stream, Cache-Control no-cache, X-Accel-Buffering no |
| `assistant.PROMPTS_DIR` | `ragassist.modules.assistant.graph.prompts` | `PROMPTS_DIR` | pathlib.Path of the versioned prompt YAML files |

### escalation

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `escalation.EscalateConversation` | `ragassist.modules.escalation.application` | `EscalateConversation` | EscalateConversation(conversations, helpdesk); async execute(principal, conversation_id, *, summary, priority) -> EscalationResult(ticket_id, status); a second call returns the existing ticket and creates none |
| `escalation.ReplyToEscalation` | `ragassist.modules.escalation.application` | `ReplyToEscalation` | ReplyToEscalation(conversations); async execute(principal, escalation_id, *, text) -> reply; only role 'agent' may reply |
| `escalation.HelpdeskClient` | `ragassist.modules.escalation.adapters.helpdesk` | `HelpdeskClient` | HelpdeskClient(http: httpx.AsyncClient); async create_ticket(principal, payload) -> dict; POST /helpdesk/tickets on the mock SaaS |
| `escalation.EscalationNotFound` | `ragassist.modules.escalation.domain` | `EscalationNotFound` | DomainError subclass; also used for another tenant's escalation (never 403) |
| `escalation.RoleNotAllowed` | `ragassist.modules.escalation.domain` | `RoleNotAllowed` | DomainError subclass |

### eval

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `eval.recall_at_k` | `evals.metrics.retrieval` | `recall_at_k` | recall_at_k(ranked, relevant, k) -> float |
| `eval.mean_reciprocal_rank` | `evals.metrics.retrieval` | `mean_reciprocal_rank` | mean_reciprocal_rank(runs: list[tuple[list[str], set[str]]]) -> float |
| `eval.ndcg_at_k` | `evals.metrics.retrieval` | `ndcg_at_k` | ndcg_at_k(ranked, gains: Mapping[str, float], k) -> float |
| `eval.brier_score` | `evals.metrics.calibration` | `brier_score` | brier_score(probs, outcomes) -> float |
| `eval.expected_calibration_error` | `evals.metrics.calibration` | `expected_calibration_error` | expected_calibration_error(probs, outcomes, *, bins=10) -> float |

### knowledge

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `knowledge.IngestionJob` | `ragassist.modules.knowledge.domain` | `IngestionJob` | IngestionJob(document_id, tenant_id, status=QUEUED, attempts=0, ...) with job_id (str) and id; frozen. Accepts id= or job_id= at construction. |
| `knowledge.JobStatus` | `ragassist.modules.knowledge.domain` | `JobStatus` | str enum: QUEUED=queued, PARSING=parsing, CHUNKING=chunking, EMBEDDING=embedding, INDEXING=indexing, COMPLETED=completed, FAILED=failed |
| `knowledge.InvalidTransition` | `ragassist.modules.knowledge.domain` | `InvalidTransition` | DomainError subclass |
| `knowledge.ParseError` | `ragassist.modules.knowledge.domain` | `ParseError` | DomainError subclass |
| `knowledge.UnsupportedMimeType` | `ragassist.modules.knowledge.domain` | `UnsupportedMimeType` | DomainError subclass (HTTP 415) |
| `knowledge.FileTooLarge` | `ragassist.modules.knowledge.domain` | `FileTooLarge` | DomainError subclass (HTTP 413) |
| `knowledge.Document` | `ragassist.modules.knowledge.domain` | `Document` | frozen dataclass (Entity: id, created_at): tenant_id (None for global), filename, content_type, file_size_bytes, s3_key, content_hash, status: DocumentStatus, error_message, metadata, updated_at |
| `knowledge.DocumentStatus` | `ragassist.modules.knowledge.domain` | `DocumentStatus` | str enum: PENDING=pending, PROCESSING=processing, COMPLETED=completed, FAILED=failed |
| `knowledge.Block` | `ragassist.modules.knowledge.domain` | `Block` | frozen dataclass: kind (heading\|paragraph\|table\|list\|code\|row), text, heading_path: tuple[str, ...] = (), page: int \| None = None |
| `knowledge.ParsedDocument` | `ragassist.modules.knowledge.domain` | `ParsedDocument` | frozen dataclass: title, blocks: list[Block] |
| `knowledge.ChunkDraft` | `ragassist.modules.knowledge.adapters.chunkers.hybrid_chunker` | `ChunkDraft` | chunk output: text (raw), embed_text (context-prefixed), heading_path, page, parent (index of the parent chunk in the returned list, or None), token_count |
| `knowledge.Chunk` | `ragassist.modules.knowledge.domain` | `Chunk` | frozen dataclass (Entity: id, created_at): document_id, tenant_id, chunk_index, content (raw text, cited), clean_text (text used for embedding and search), token_count, heading_path: list[str], page_number, parent_id: UUID \| None, content_hash, injection_flag, metadata |
| `knowledge.LEGAL_TRANSITIONS` | `ragassist.modules.knowledge.domain` | `LEGAL_JOB_TRANSITIONS` | set of (from, to) status-value pairs that transition_job accepts |
| `knowledge.Parser` | `ragassist.modules.knowledge.domain` | `Parser` | Protocol: supports(mime: str) -> bool; parse(content: bytes, *, mime: str, filename: str) -> ParsedDocument |
| `knowledge.Chunker` | `ragassist.modules.knowledge.domain` | `Chunker` | Protocol: chunk(parsed: ParsedDocument, *, title: str) -> list of ChunkDraft (synchronous) |
| `knowledge.transition_job` | `ragassist.modules.knowledge.domain` | `transition_job` | transition_job(current_job, target) -> IngestionJob (a new frozen job via dataclasses.replace); raises InvalidTransition for any pair not in LEGAL_TRANSITIONS |
| `knowledge.UploadCommand` | `ragassist.modules.knowledge.application` | `UploadCommand` | tenant_id, user_id, filename: str, mime: str, content: bytes |
| `knowledge.UploadResult` | `ragassist.modules.knowledge.application` | `UploadResult` | job_id, document_id, object_key |
| `knowledge.UploadDocument` | `ragassist.modules.knowledge.application` | `UploadDocument` | UploadDocument(store: ObjectStore, queue: MessageQueue, documents, max_bytes, allowed_mimes, queue_name); async execute(command) -> UploadResult. Stores with store.put_object(key, data, content_type=...). Object key starts with tenants/<tenant_id>/. Sends a dict body (job_id, tenant_id, object_key) with queue.send_message. A failed put or send leaves no job row and no object. |
| `knowledge.ProcessIngestionJob` | `ragassist.modules.knowledge.application` | `ProcessIngestionJob` | ProcessIngestionJob(documents, store: ObjectStore, parsers: Mapping[str, Parser], chunker: Chunker, embedder, max_retries); async handle(body: dict) -> IngestOutcome. The body is the queue message dict (job_id, tenant_id, object_key, document_id). Claims the job before work; replace_chunks is all-or-nothing. |
| `knowledge.IngestOutcome` | `ragassist.modules.knowledge.application` | `IngestOutcome` | enum: COMPLETED, DUPLICATE_SKIPPED, RETRY, DEAD_LETTERED, REJECTED |
| `knowledge.ChunkModel` | `ragassist.modules.knowledge.adapters.persistence.models` | `ChunkModel` | ORM model: id, tenant_id (nullable for global docs), document_id, text, embed_text, heading_path, embedding vector(dim), fts tsvector; used by integration seeding |
| `knowledge.parser.markdown` | `ragassist.modules.knowledge.adapters.parsers.markdown` | `MarkdownParser` | MarkdownParser: supports(mime) -> bool; parse(content, *, mime, filename) -> ParsedDocument with Block objects |
| `knowledge.parser.html` | `ragassist.modules.knowledge.adapters.parsers.html` | `HtmlParser` | same protocol; tables become table blocks in markdown form |
| `knowledge.parser.pymupdf` | `ragassist.modules.knowledge.adapters.parsers.pymupdf` | `PyMuPDFParser` | same protocol; blocks per page with page=<1-based page number> |
| `knowledge.parser.tabular` | `ragassist.modules.knowledge.adapters.parsers.tabular` | `TabularParser` | same protocol; CSV rows become row blocks whose text repeats the header |
| `knowledge.parser.docling` | `ragassist.modules.knowledge.adapters.parsers.docling` | `DoclingParser` | same protocol (v2 adapter; needs the docling extra) |
| `knowledge.chunker.hybrid` | `ragassist.modules.knowledge.adapters.chunkers.hybrid` | `HybridChunker` | HybridChunker(max_tokens, overlap_tokens, merge_peers, tokenizer, parent_child=False, semantic=False, semantic_embedder=None); from_settings(settings, tokenizer) reads CHUNK_* settings; chunk(parsed: ParsedDocument, *, title) -> list[ChunkDraft] (synchronous); tokenizer.count(text) -> int |
| `knowledge.chunker.recursive` | `ragassist.modules.knowledge.adapters.chunkers.recursive` | `RecursiveChunker` | RecursiveChunker(max_tokens, overlap_tokens, tokenizer); same chunk() protocol |
| `knowledge.chunker.docling_hybrid` | `ragassist.modules.knowledge.adapters.chunkers.docling_hybrid` | `DoclingHybridChunker` | DoclingHybridChunker(max_tokens, tokenizer); same chunk() protocol (v2, needs docling) |
| `knowledge.pass.structure` | `ragassist.modules.knowledge.adapters.chunkers.passes` | `structure_pass` | structure_pass(parsed: ParsedDocument) -> list[Block]: one block per logical element; heading_path kept |
| `knowledge.pass.token` | `ragassist.modules.knowledge.adapters.chunkers.passes` | `token_pass` | token_pass(blocks, *, max_tokens, tokenizer) -> list[Block]: splits oversized non-table blocks at sentence boundaries |
| `knowledge.pass.merge` | `ragassist.modules.knowledge.adapters.chunkers.passes` | `merge_pass` | merge_pass(blocks, *, max_tokens, tokenizer) -> list[Block]: merges adjacent blocks with the same heading_path while within max_tokens |
| `knowledge.pass.table` | `ragassist.modules.knowledge.adapters.chunkers.passes` | `table_pass` | table_pass(blocks, *, max_tokens, tokenizer) -> list[Block]: a table that fits stays whole; otherwise split by rows, each part repeating the header row |
| `knowledge.pass.context` | `ragassist.modules.knowledge.adapters.chunkers.passes` | `context_pass` | context_pass(blocks, *, title) -> list[ChunkDraft]: embed_text = "[Document: <title> \| Section: <a > b>]" + newline + text; text stays raw |

### queue

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `queue.MessageQueue` | `ragassist.platform.storage.ports` | `MessageQueue` | Protocol: async send_message(queue_name, message_body: dict, delay_seconds=0) -> str; async receive_messages(queue_name, max_messages=10, wait_time_seconds=10) -> list[dict] with message_id, receipt_handle, body; async delete_message(queue_name, receipt_handle) -> bool |
| `queue.sqs` | `ragassist.platform.queue.sqs_adapter` | `SQSMessageQueue` | SQSMessageQueue(settings): the MessageQueue port over SQS; visibility timeout and redrive are SQS behaviour |
| `queue.memory` | `ragassist.platform.queue.sqs_adapter` | `InMemoryMessageQueue` | in-memory MessageQueue: receive peeks (messages stay until deleted); delete_message returns True; no visibility timeout or dead letter (SQS semantics, covered by the LocalStack integration tests) |

### rerank

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `rerank.Candidate` | `ragassist.platform.rerank.ports` | `Candidate` | chunk_id: str; text: str; score: float (input order score) |
| `rerank.Scored` | `ragassist.platform.rerank.ports` | `Scored` | chunk_id: str; score: float |
| `rerank.build_reranker_chain` | `ragassist.platform.rerank.service` | `build_reranker_chain` | build_reranker_chain(settings, instances: Mapping[str, Reranker] \| None = None) -> RerankerChain; instances override registry construction (for tests). RerankerChain.async rerank(query, candidates, *, top_n) -> ChainResult(items, reranker) |
| `rerank.NoopReranker` | `ragassist.platform.rerank.adapters.noop` | `NoopReranker` | name 'none'; rerank keeps the input order and scores |
| `rerank.FlashRankReranker` | `ragassist.platform.rerank.adapters.flashrank` | `FlashRankReranker` | FlashRankReranker(model_name): name 'flashrank'; async rerank(query, candidates, *, top_n) |
| `rerank.CrossEncoderReranker` | `ragassist.platform.rerank.adapters.cross_encoder` | `CrossEncoderReranker` | CrossEncoderReranker(model_name, device=None): name 'cross_encoder'; scoring runs via run_cpu_bound; loads sentence_transformers.CrossEncoder |
| `rerank.ApiReranker` | `ragassist.platform.rerank.adapters.api` | `ApiReranker` | ApiReranker(base_url, api_key, model, http: httpx.AsyncClient): name 'api'; POST {base}/rerank |
| `rerank.DecisionReranker` | `ragassist.platform.rerank.adapters.decision` | `DecisionReranker` | DecisionReranker(decider): name 'decision'; scores each candidate with a ScoreQuestion |

### retrieval

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `retrieval.reciprocal_rank_fusion` | `ragassist.modules.retrieval.domain` | `reciprocal_rank_fusion` | reciprocal_rank_fusion(rankings: list[list[str]], *, k=60) -> list[tuple[str, float]] sorted by score descending, ties by first appearance; an id repeated inside one ranking counts at its best rank only |
| `retrieval.Hit` | `ragassist.modules.retrieval.domain` | `Hit` | chunk_id, document_id, tenant_id (None for global), score, text, heading_path, page, title (title of the owning document, used for citations) |
| `retrieval.RetrievedChunk` | `ragassist.modules.retrieval.domain` | `RetrievedChunk` | PROJECT.md section 4 DTO: chunk_id, document_id, content, score, heading_path: str \| None (see conflict C-R1), page_number, metadata |
| `retrieval.RetrievalService` | `ragassist.modules.retrieval.application` | `RetrievalService` | PROJECT.md section 4 protocol: async retrieve(tenant_id, query, top_k=6) -> list[RetrievedChunk] |
| `retrieval.HybridRetriever` | `ragassist.modules.retrieval.application` | `HybridRetriever` | HybridRetriever(dense, sparse, rrf_k=60); async search(query, *, tenant_id, k, filters=None) -> list[Hit]; a retriever that returns nothing does not stop the other |
| `retrieval.ContextBuilder` | `ragassist.modules.retrieval.application` | `ContextBuilder` | ContextBuilder(tokenizer, budget_tokens); build(hits) -> ContextPack(passages: list[Passage(chunk_id, text, citation: Citation(title, page, heading_path))]) |
| `retrieval.VectorRetriever` | `ragassist.modules.retrieval.adapters.vector` | `VectorRetriever` | VectorRetriever(embedder, session_factory); cosine distance on chunk embeddings; runs in its own UnitOfWork |
| `retrieval.KeywordRetriever` | `ragassist.modules.retrieval.adapters.keyword` | `KeywordRetriever` | KeywordRetriever(session_factory, backend='fts'); websearch_to_tsquery over the tsvector |

### storage

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `storage.ObjectStore` | `ragassist.platform.storage.ports` | `ObjectStore` | Protocol: async put_object(key, data, content_type=..., metadata=None) -> str (URI); async get_object(key) -> bytes; async delete_object(key) -> bool |
| `storage.s3` | `ragassist.platform.storage.s3_adapter` | `S3ObjectStore` | S3ObjectStore(settings): the ObjectStore port over S3 (LocalStack in tests) |
| `storage.memory` | `ragassist.platform.storage.s3_adapter` | `InMemoryObjectStore` | in-memory ObjectStore: put returns mem://key; get on a missing key raises KeyError; delete returns False when the key is absent |

### worker

| Key | Module | Symbol | Interface the tests assume |
|---|---|---|---|
| `worker.IngestionWorker` | `ragassist.worker.main` | `IngestionWorker` | IngestionWorker(queue: MessageQueue, queue_name, handler, concurrency=4, wait_time_seconds=0); async run_until_stopped(stop: asyncio.Event): receive_messages, handler(body) -> IngestOutcome, delete_message on COMPLETED / DUPLICATE_SKIPPED / REJECTED / DEAD_LETTERED, leave the message on RETRY; finishes in-flight work before returning |

### HTTP routes

| Key | Method | Path |
|---|---|---|
| `health` | GET | `/healthz` |
| `dev_token` | POST | `/v1/auth/token` |
| `list_documents` | GET | `/v1/documents` |
| `upload_document` | POST | `/v1/documents` |
| `ingestion_job` | GET | `/v1/ingestion-jobs/{job_id}` |
| `ask_message` | POST | `/v1/conversations/{conversation_id}/messages` |
| `escalation_reply` | POST | `/v1/escalations/{escalation_id}/replies` |
<!-- appendix:end -->
