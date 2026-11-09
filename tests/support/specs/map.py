"""Planned production symbols, named in ONE place.

Each entry follows implementation_plan.md section 9 and the ADRs. ``expects`` is the interface the
tests assume. When the implementation team's real signatures differ, the suite reports DRIFT, and
the fix is one of two small edits: a renamed symbol changes here, a changed call changes in the
test. ``render_appendix()`` turns this map into the interface appendix of docs/testing.md, which is
the document the implementation team builds against.
"""

from __future__ import annotations

from dataclasses import dataclass

K = "ragassist.modules.knowledge"
R = "ragassist.modules.retrieval"
A = "ragassist.modules.assistant"
AC = "ragassist.modules.actions"
E = "ragassist.modules.escalation"
P = "ragassist.platform"


@dataclass(frozen=True)
class Target:
    area: str
    module: str
    symbol: str
    expects: str
    renamed_from: tuple[str, ...] = ()


def _t(
    area: str, module: str, symbol: str, expects: str, renamed_from: tuple[str, ...] = ()
) -> Target:
    return Target(area, module, symbol, expects, renamed_from)


TARGETS: dict[str, Target] = {
    # ------------------------------------------------------------------ knowledge: domain
    "knowledge.IngestionJob": _t(
        "knowledge",
        f"{K}.domain",
        "IngestionJob",
        "IngestionJob(document_id, tenant_id, status=QUEUED, attempts=0, ...) with job_id (str) and id; frozen. Accepts id= or job_id= at construction.",
    ),
    "knowledge.JobStatus": _t(
        "knowledge",
        f"{K}.domain",
        "JobStatus",
        "str enum: QUEUED=queued, PARSING=parsing, CHUNKING=chunking, EMBEDDING=embedding, INDEXING=indexing, COMPLETED=completed, FAILED=failed",
    ),
    "knowledge.InvalidTransition": _t(
        "knowledge", f"{K}.domain", "InvalidTransition", "DomainError subclass"
    ),
    "knowledge.ParseError": _t("knowledge", f"{K}.domain", "ParseError", "DomainError subclass"),
    "knowledge.UnsupportedMimeType": _t(
        "knowledge", f"{K}.domain", "UnsupportedMimeType", "DomainError subclass (HTTP 415)"
    ),
    "knowledge.FileTooLarge": _t(
        "knowledge", f"{K}.domain", "FileTooLarge", "DomainError subclass (HTTP 413)"
    ),
    "knowledge.Document": _t(
        "knowledge",
        f"{K}.domain",
        "Document",
        "frozen dataclass (Entity: id, created_at): tenant_id (None for global), filename, content_type, file_size_bytes, s3_key, content_hash, status: DocumentStatus, error_message, metadata, updated_at",
    ),
    "knowledge.DocumentStatus": _t(
        "knowledge",
        f"{K}.domain",
        "DocumentStatus",
        "str enum: PENDING=pending, PROCESSING=processing, COMPLETED=completed, FAILED=failed",
    ),
    "knowledge.Block": _t(
        "knowledge",
        f"{K}.domain",
        "Block",
        "frozen dataclass: kind (heading|paragraph|table|list|code|row), text, heading_path: tuple[str, ...] = (), page: int | None = None",
    ),
    "knowledge.ParsedDocument": _t(
        "knowledge",
        f"{K}.domain",
        "ParsedDocument",
        "frozen dataclass: title, blocks: list[Block]",
    ),
    "knowledge.ChunkDraft": _t(
        "knowledge",
        f"{K}.adapters.chunkers.hybrid_chunker",
        "ChunkDraft",
        "chunk output: text (raw), embed_text (context-prefixed), heading_path, page, parent (index of the parent chunk in the returned list, or None), token_count",
    ),
    "knowledge.Chunk": _t(
        "knowledge",
        f"{K}.domain",
        "Chunk",
        "frozen dataclass (Entity: id, created_at): document_id, tenant_id, chunk_index, content (raw text, cited), clean_text (text used for embedding and search), token_count, heading_path: list[str], page_number, parent_id: UUID | None, content_hash, injection_flag, metadata",
    ),
    "knowledge.LEGAL_TRANSITIONS": _t(
        "knowledge",
        f"{K}.domain",
        "LEGAL_JOB_TRANSITIONS",
        "set of (from, to) status-value pairs that transition_job accepts",
        ("LEGAL_TRANSITIONS",),
    ),
    "knowledge.Parser": _t(
        "knowledge",
        f"{K}.domain",
        "Parser",
        "Protocol: supports(mime: str) -> bool; parse(content: bytes, *, mime: str, filename: str) -> ParsedDocument",
    ),
    "knowledge.Chunker": _t(
        "knowledge",
        f"{K}.domain",
        "Chunker",
        "Protocol: chunk(parsed: ParsedDocument, *, title: str) -> list of ChunkDraft (synchronous)",
    ),
    "knowledge.transition_job": _t(
        "knowledge",
        f"{K}.domain",
        "transition_job",
        "transition_job(current_job, target) -> IngestionJob (a new frozen job via dataclasses.replace); raises InvalidTransition for any pair not in LEGAL_TRANSITIONS",
    ),
    # ------------------------------------------------------------------ knowledge: application
    "knowledge.UploadCommand": _t(
        "knowledge",
        f"{K}.application",
        "UploadCommand",
        "tenant_id, user_id, filename: str, mime: str, content: bytes",
    ),
    "knowledge.UploadResult": _t(
        "knowledge", f"{K}.application", "UploadResult", "job_id, document_id, object_key"
    ),
    "knowledge.UploadDocument": _t(
        "knowledge",
        f"{K}.application",
        "UploadDocument",
        "UploadDocument(store: ObjectStore, queue: MessageQueue, documents, max_bytes, allowed_mimes, queue_name); async execute(command) -> UploadResult. Stores with store.put_object(key, data, content_type=...). Object key starts with tenants/<tenant_id>/. Sends a dict body (job_id, tenant_id, object_key) with queue.send_message. A failed put or send leaves no job row and no object.",
    ),
    "knowledge.ProcessIngestionJob": _t(
        "knowledge",
        f"{K}.application",
        "ProcessIngestionJob",
        "ProcessIngestionJob(documents, store: ObjectStore, parsers: Mapping[str, Parser], chunker: Chunker, embedder, max_retries); async handle(body: dict) -> IngestOutcome. The body is the queue message dict (job_id, tenant_id, object_key, document_id). Claims the job before work; replace_chunks is all-or-nothing.",
    ),
    "knowledge.IngestOutcome": _t(
        "knowledge",
        f"{K}.application",
        "IngestOutcome",
        "enum: COMPLETED, DUPLICATE_SKIPPED, RETRY, DEAD_LETTERED, REJECTED",
    ),
    "knowledge.ChunkModel": _t(
        "knowledge",
        f"{K}.adapters.persistence.models",
        "ChunkModel",
        "ORM model: id, tenant_id (nullable for global docs), document_id, text, embed_text, "
        "heading_path, embedding vector(dim), fts tsvector; used by integration seeding",
    ),
    # ------------------------------------------------------------------ knowledge: parsers
    "knowledge.parser.markdown": _t(
        "knowledge",
        f"{K}.adapters.parsers.markdown",
        "MarkdownParser",
        "MarkdownParser: supports(mime) -> bool; parse(content, *, mime, filename) -> ParsedDocument with Block objects",
    ),
    "knowledge.parser.html": _t(
        "knowledge",
        f"{K}.adapters.parsers.html",
        "HtmlParser",
        "same protocol; tables become table blocks in markdown form",
    ),
    "knowledge.parser.pymupdf": _t(
        "knowledge",
        f"{K}.adapters.parsers.pymupdf",
        "PyMuPDFParser",
        "same protocol; blocks per page with page=<1-based page number>",
    ),
    "knowledge.parser.tabular": _t(
        "knowledge",
        f"{K}.adapters.parsers.tabular",
        "TabularParser",
        "same protocol; CSV rows become row blocks whose text repeats the header",
    ),
    "knowledge.parser.docling": _t(
        "knowledge",
        f"{K}.adapters.parsers.docling",
        "DoclingParser",
        "same protocol (v2 adapter; needs the docling extra)",
    ),
    # ------------------------------------------------------------------ knowledge: chunkers
    "knowledge.chunker.hybrid": _t(
        "knowledge",
        f"{K}.adapters.chunkers.hybrid",
        "HybridChunker",
        "HybridChunker(max_tokens, overlap_tokens, merge_peers, tokenizer, parent_child=False, semantic=False, semantic_embedder=None); from_settings(settings, tokenizer) reads CHUNK_* settings; chunk(parsed: ParsedDocument, *, title) -> list[ChunkDraft] (synchronous); tokenizer.count(text) -> int",
    ),
    "knowledge.chunker.recursive": _t(
        "knowledge",
        f"{K}.adapters.chunkers.recursive",
        "RecursiveChunker",
        "RecursiveChunker(max_tokens, overlap_tokens, tokenizer); same chunk() protocol",
    ),
    "knowledge.chunker.docling_hybrid": _t(
        "knowledge",
        f"{K}.adapters.chunkers.docling_hybrid",
        "DoclingHybridChunker",
        "DoclingHybridChunker(max_tokens, tokenizer); same chunk() protocol (v2, needs docling)",
    ),
    # ------------------------------------------------------------------ knowledge: the five passes
    "knowledge.pass.structure": _t(
        "knowledge",
        f"{K}.adapters.chunkers.passes",
        "structure_pass",
        "structure_pass(parsed: ParsedDocument) -> list[Block]: one block per logical element; heading_path kept",
    ),
    "knowledge.pass.token": _t(
        "knowledge",
        f"{K}.adapters.chunkers.passes",
        "token_pass",
        "token_pass(blocks, *, max_tokens, tokenizer) -> list[Block]: splits oversized non-table blocks at sentence boundaries",
    ),
    "knowledge.pass.merge": _t(
        "knowledge",
        f"{K}.adapters.chunkers.passes",
        "merge_pass",
        "merge_pass(blocks, *, max_tokens, tokenizer) -> list[Block]: merges adjacent blocks with the same heading_path while within max_tokens",
    ),
    "knowledge.pass.table": _t(
        "knowledge",
        f"{K}.adapters.chunkers.passes",
        "table_pass",
        "table_pass(blocks, *, max_tokens, tokenizer) -> list[Block]: a table that fits stays whole; otherwise split by rows, each part repeating the header row",
    ),
    "knowledge.pass.context": _t(
        "knowledge",
        f"{K}.adapters.chunkers.passes",
        "context_pass",
        'context_pass(blocks, *, title) -> list[ChunkDraft]: embed_text = "[Document: <title> | Section: <a > b>]" + newline + text; text stays raw',
    ),
    # ------------------------------------------------------------------ platform: rerank
    "rerank.Candidate": _t(
        "rerank",
        f"{P}.rerank.ports",
        "Candidate",
        "chunk_id: str; text: str; score: float (input order score)",
    ),
    "rerank.Scored": _t("rerank", f"{P}.rerank.ports", "Scored", "chunk_id: str; score: float"),
    "rerank.build_reranker_chain": _t(
        "rerank",
        f"{P}.rerank.service",
        "build_reranker_chain",
        "build_reranker_chain(settings, instances: Mapping[str, Reranker] | None = None) -> "
        "RerankerChain; instances override registry construction (for tests). "
        "RerankerChain.async rerank(query, candidates, *, top_n) -> ChainResult(items, reranker)",
    ),
    "rerank.NoopReranker": _t(
        "rerank",
        f"{P}.rerank.adapters.noop",
        "NoopReranker",
        "name 'none'; rerank keeps the input order and scores",
    ),
    "rerank.FlashRankReranker": _t(
        "rerank",
        f"{P}.rerank.adapters.flashrank",
        "FlashRankReranker",
        "FlashRankReranker(model_name): name 'flashrank'; async rerank(query, candidates, *, top_n)",
    ),
    "rerank.CrossEncoderReranker": _t(
        "rerank",
        f"{P}.rerank.adapters.cross_encoder",
        "CrossEncoderReranker",
        "CrossEncoderReranker(model_name, device=None): name 'cross_encoder'; scoring runs via "
        "run_cpu_bound; loads sentence_transformers.CrossEncoder",
    ),
    "rerank.ApiReranker": _t(
        "rerank",
        f"{P}.rerank.adapters.api",
        "ApiReranker",
        "ApiReranker(base_url, api_key, model, http: httpx.AsyncClient): name 'api'; POST {base}/rerank",
    ),
    "rerank.DecisionReranker": _t(
        "rerank",
        f"{P}.rerank.adapters.decision",
        "DecisionReranker",
        "DecisionReranker(decider): name 'decision'; scores each candidate with a ScoreQuestion",
    ),
    # ------------------------------------------------------------------ platform: storage, queue
    "storage.ObjectStore": _t(
        "storage",
        f"{P}.storage.ports",
        "ObjectStore",
        "Protocol: async put_object(key, data, content_type=..., metadata=None) -> str (URI); async get_object(key) -> bytes; async delete_object(key) -> bool",
    ),
    "storage.s3": _t(
        "storage",
        f"{P}.storage.s3_adapter",
        "S3ObjectStore",
        "S3ObjectStore(settings): the ObjectStore port over S3 (LocalStack in tests)",
    ),
    "storage.memory": _t(
        "storage",
        f"{P}.storage.s3_adapter",
        "InMemoryObjectStore",
        "in-memory ObjectStore: put returns mem://key; get on a missing key raises KeyError; delete returns False when the key is absent",
    ),
    "queue.MessageQueue": _t(
        "queue",
        f"{P}.storage.ports",
        "MessageQueue",
        "Protocol: async send_message(queue_name, message_body: dict, delay_seconds=0) -> str; async receive_messages(queue_name, max_messages=10, wait_time_seconds=10) -> list[dict] with message_id, receipt_handle, body; async delete_message(queue_name, receipt_handle) -> bool",
    ),
    "queue.sqs": _t(
        "queue",
        f"{P}.queue.sqs_adapter",
        "SQSMessageQueue",
        "SQSMessageQueue(settings): the MessageQueue port over SQS; visibility timeout and redrive are SQS behaviour",
    ),
    "queue.memory": _t(
        "queue",
        f"{P}.queue.sqs_adapter",
        "InMemoryMessageQueue",
        "in-memory MessageQueue: receive peeks (messages stay until deleted); delete_message returns True; no visibility timeout or dead letter (SQS semantics, covered by the LocalStack integration tests)",
    ),
    # ------------------------------------------------------------------ retrieval
    "retrieval.reciprocal_rank_fusion": _t(
        "retrieval",
        f"{R}.domain",
        "reciprocal_rank_fusion",
        "reciprocal_rank_fusion(rankings: list[list[str]], *, k=60) -> list[tuple[str, float]] sorted by "
        "score descending, ties by first appearance; an id repeated inside one ranking counts at its "
        "best rank only",
    ),
    "retrieval.Hit": _t(
        "retrieval",
        f"{R}.domain",
        "Hit",
        "chunk_id, document_id, tenant_id (None for global), score, text, heading_path, page, title "
        "(title of the owning document, used for citations)",
    ),
    "retrieval.RetrievedChunk": _t(
        "retrieval",
        "ragassist.modules.retrieval.domain",
        "RetrievedChunk",
        "PROJECT.md section 4 DTO: chunk_id, document_id, content, score, heading_path: str | None (see conflict C-R1), "
        "page_number, metadata",
    ),
    "retrieval.RetrievalService": _t(
        "retrieval",
        "ragassist.modules.retrieval.application",
        "RetrievalService",
        "PROJECT.md section 4 protocol: async retrieve(tenant_id, query, top_k=6) -> list[RetrievedChunk]",
    ),
    "retrieval.HybridRetriever": _t(
        "retrieval",
        f"{R}.application",
        "HybridRetriever",
        "HybridRetriever(dense, sparse, rrf_k=60); async search(query, *, tenant_id, k, filters=None) "
        "-> list[Hit]; a retriever that returns nothing does not stop the other",
    ),
    "retrieval.ContextBuilder": _t(
        "retrieval",
        f"{R}.application",
        "ContextBuilder",
        "ContextBuilder(tokenizer, budget_tokens); build(hits) -> ContextPack(passages: "
        "list[Passage(chunk_id, text, citation: Citation(title, page, heading_path))])",
    ),
    "retrieval.VectorRetriever": _t(
        "retrieval",
        f"{R}.adapters.vector",
        "VectorRetriever",
        "VectorRetriever(embedder, session_factory); cosine distance on chunk embeddings; runs in its own "
        "UnitOfWork",
    ),
    "retrieval.KeywordRetriever": _t(
        "retrieval",
        f"{R}.adapters.keyword",
        "KeywordRetriever",
        "KeywordRetriever(session_factory, backend='fts'); websearch_to_tsquery over the tsvector",
    ),
    # ------------------------------------------------------------------ evaluation metrics
    "eval.recall_at_k": _t(
        "eval",
        "evals.metrics.retrieval",
        "recall_at_k",
        "recall_at_k(ranked, relevant, k) -> float",
    ),
    "eval.mean_reciprocal_rank": _t(
        "eval",
        "evals.metrics.retrieval",
        "mean_reciprocal_rank",
        "mean_reciprocal_rank(runs: list[tuple[list[str], set[str]]]) -> float",
    ),
    "eval.ndcg_at_k": _t(
        "eval",
        "evals.metrics.retrieval",
        "ndcg_at_k",
        "ndcg_at_k(ranked, gains: Mapping[str, float], k) -> float",
    ),
    "eval.brier_score": _t(
        "eval", "evals.metrics.calibration", "brier_score", "brier_score(probs, outcomes) -> float"
    ),
    "eval.expected_calibration_error": _t(
        "eval",
        "evals.metrics.calibration",
        "expected_calibration_error",
        "expected_calibration_error(probs, outcomes, *, bins=10) -> float",
    ),
    # ------------------------------------------------------------------ assistant
    "assistant.build_graph": _t(
        "assistant",
        f"{A}.graph.builder",
        "build_graph",
        "build_graph(*, settings, decision_service, generator_tiers: Mapping[str, BaseChatModel], "
        "retriever, reranker, tools, checkpointer) -> compiled LangGraph. Node names are the plan's: "
        "guard_input, router, rewrite, hybrid_retrieve, rerank, grade_relevance, account_agent, "
        "generate, verify_grounding, escalate, finalize. Final state keys: answer, route, citations, "
        "escalated, status, model_used, decider_used, complexity, tool_calls",
    ),
    "assistant.NODE_NAMES": _t(
        "assistant", f"{A}.graph.builder", "NODE_NAMES", "tuple of every node name in the graph"
    ),
    "assistant.namespaced_thread_id": _t(
        "assistant",
        f"{A}.application.thread_guard",
        "namespaced_thread_id",
        "namespaced_thread_id(tenant_id, conversation_id) -> '<tenant_id>:<conversation_id>'",
    ),
    "assistant.ensure_thread_access": _t(
        "assistant",
        f"{A}.application.thread_guard",
        "ensure_thread_access",
        "async ensure_thread_access(principal, conversation_id, conversations) -> None; raises "
        "ThreadAccessDenied before any checkpoint read",
    ),
    "assistant.ThreadAccessDenied": _t(
        "assistant", f"{A}.application.thread_guard", "ThreadAccessDenied", "DomainError subclass"
    ),
    "assistant.sse_stream": _t(
        "assistant",
        f"{A}.api.sse",
        "sse_stream",
        "sse_stream(events: AsyncIterator[dict], *, heartbeat_seconds) -> AsyncIterator[str]: yields SSE "
        "frames (event:/data:/id: lines); a ': ping' comment when idle for heartbeat_seconds; closing "
        "the output closes the source",
    ),
    "assistant.SSE_HEADERS": _t(
        "assistant",
        f"{A}.api.sse",
        "SSE_HEADERS",
        "dict with Content-Type text/event-stream, Cache-Control no-cache, X-Accel-Buffering no",
    ),
    "assistant.PROMPTS_DIR": _t(
        "assistant",
        f"{A}.graph.prompts",
        "PROMPTS_DIR",
        "pathlib.Path of the versioned prompt YAML files",
    ),
    "worker.IngestionWorker": _t(
        "worker",
        "ragassist.worker.main",
        "IngestionWorker",
        "IngestionWorker(queue: MessageQueue, queue_name, handler, concurrency=4, wait_time_seconds=0); async run_until_stopped(stop: asyncio.Event): receive_messages, handler(body) -> IngestOutcome, delete_message on COMPLETED / DUPLICATE_SKIPPED / REJECTED / DEAD_LETTERED, leave the message on RETRY; finishes in-flight work before returning",
    ),
    # ------------------------------------------------------------------ actions
    "actions.ToolSpec": _t(
        "actions",
        f"{AC}.application",
        "ToolSpec",
        "ToolSpec(name, description, input_schema: dict, is_write: bool, handler); handler(principal, arguments) is async",
    ),
    "actions.ToolRegistry": _t(
        "actions",
        f"{AC}.application",
        "ToolRegistry",
        "ToolRegistry(tools); schemas() -> list[dict]; async invoke(name, arguments, principal) -> Any; "
        "validates arguments against input_schema before the handler runs; the tenant and user always come "
        "from the principal, never from arguments; raises UnknownTool",
    ),
    "actions.UnknownTool": _t(
        "actions", f"{AC}.application", "UnknownTool", "DomainError subclass"
    ),
    "actions.default_tools": _t(
        "actions",
        f"{AC}.tools",
        "default_tools",
        "default_tools(saas: SaaSClient) -> list[ToolSpec]: the production tool set",
    ),
    "actions.ApprovalPolicy": _t(
        "actions",
        f"{AC}.application",
        "ApprovalPolicy",
        "ApprovalPolicy(intent_check=None); requires_approval(tool) -> bool: writes always True, reads "
        "always False; intent_check never replaces approval",
    ),
    "actions.AuditLog": _t(
        "actions",
        f"{AC}.application",
        "AuditLog",
        "AuditLog(store); async record(principal, tool, arguments, *, approved, outcome, uow) -> entry "
        "(secrets masked); list_for_tenant(tenant_id) -> list",
    ),
    "actions.SaaSClient": _t(
        "actions",
        f"{AC}.adapters.saas_client",
        "SaaSClient",
        "SaaSClient(http: httpx.AsyncClient, max_retries=2, backoff_seconds=0.0, sleep=None); async get_overview, "
        "get_subscription, get_invoices, update_billing_email(email), create_ticket(payload) all take "
        "principal first; forwards principal.raw_token as a Bearer token; GET retried on 5xx, POST not",
    ),
    "actions.SaaSClientError": _t(
        "actions", f"{AC}.adapters.saas_client", "SaaSClientError", ".status_code; 4xx responses"
    ),
    "actions.SaaSUnavailable": _t(
        "actions", f"{AC}.adapters.saas_client", "SaaSUnavailable", "5xx after retries"
    ),
    "actions.SaaSTimeout": _t(
        "actions", f"{AC}.adapters.saas_client", "SaaSTimeout", "transport timeout"
    ),
    "actions.SaaSResponseInvalid": _t(
        "actions", f"{AC}.adapters.saas_client", "SaaSResponseInvalid", "2xx body fails the schema"
    ),
    # ------------------------------------------------------------------ escalation
    "escalation.EscalateConversation": _t(
        "escalation",
        f"{E}.application",
        "EscalateConversation",
        "EscalateConversation(conversations, helpdesk); async execute(principal, conversation_id, *, "
        "summary, priority) -> EscalationResult(ticket_id, status); a second call returns the existing "
        "ticket and creates none",
    ),
    "escalation.ReplyToEscalation": _t(
        "escalation",
        f"{E}.application",
        "ReplyToEscalation",
        "ReplyToEscalation(conversations); async execute(principal, escalation_id, *, text) -> reply; "
        "only role 'agent' may reply",
    ),
    "escalation.HelpdeskClient": _t(
        "escalation",
        f"{E}.adapters.helpdesk",
        "HelpdeskClient",
        "HelpdeskClient(http: httpx.AsyncClient); async create_ticket(principal, payload) -> dict; "
        "POST /helpdesk/tickets on the mock SaaS",
    ),
    "escalation.EscalationNotFound": _t(
        "escalation",
        f"{E}.domain",
        "EscalationNotFound",
        "DomainError subclass; also used for another tenant's escalation (never 403)",
    ),
    "escalation.RoleNotAllowed": _t(
        "escalation", f"{E}.domain", "RoleNotAllowed", "DomainError subclass"
    ),
}

#: HTTP routes the security and SSE suites exercise. Value: (method, path template).
ROUTES: dict[str, tuple[str, str]] = {
    "health": ("GET", "/healthz"),
    "dev_token": ("POST", "/v1/auth/token"),
    "list_documents": ("GET", "/v1/documents"),
    "upload_document": ("POST", "/v1/documents"),
    "ingestion_job": ("GET", "/v1/ingestion-jobs/{job_id}"),
    "ask_message": ("POST", "/v1/conversations/{conversation_id}/messages"),
    "escalation_reply": ("POST", "/v1/escalations/{escalation_id}/replies"),
}


def render_appendix() -> str:
    """Markdown for the interface appendix of docs/testing.md (generated; never edit by hand)."""
    lines: list[str] = []
    areas: dict[str, list[tuple[str, Target]]] = {}
    for key, target in TARGETS.items():
        areas.setdefault(target.area, []).append((key, target))
    for area in sorted(areas):
        lines.append(f"### {area}")
        lines.append("")
        lines.append("| Key | Module | Symbol | Interface the tests assume |")
        lines.append("|---|---|---|---|")
        for key, target in areas[area]:
            expects = target.expects.replace("|", "\\|")
            lines.append(f"| `{key}` | `{target.module}` | `{target.symbol}` | {expects} |")
        lines.append("")
    lines.append("### HTTP routes")
    lines.append("")
    lines.append("| Key | Method | Path |")
    lines.append("|---|---|---|")
    for key, (method, path) in ROUTES.items():
        lines.append(f"| `{key}` | {method} | `{path}` |")
    lines.append("")
    return "\n".join(lines)
