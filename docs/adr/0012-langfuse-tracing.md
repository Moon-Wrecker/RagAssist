# ADR 0012: Langfuse Tracing of Assistant Turns, with Redaction Before Export

## Context & Problem
A turn runs about five to seven model calls (safety, routing, rewrite, grading, generation, grounding), a query
embedding, a hybrid search and a rerank. When an answer is wrong or slow nothing shows which step did it. We want one
readable trace per turn, grouped by conversation and user, without ever exporting a credential. The graph input carries
the signed-in principal including its bearer token, so naive callback tracing would leak it.

## Decision
1. **One trace per turn.** The router opens a root `agent` observation (`answer-question`, or `decide-action` for an
   approval) whose input is the user's question and whose output is the answer. `session_id` is the conversation id,
   `user_id` the user's UUID, tags are `assistant` and the mode (`stream`, `json`, `approval`), and `tenant_id` and
   `role` travel as metadata (filterable without becoming a high-cardinality tag). The environment is `APP_ENV`.
2. **Framework integration, not hand-written spans.** Langfuse's LangChain `CallbackHandler` is added to the graph run
   config, so nodes, model calls (model name, token usage) and tools nest under the root automatically. Our own
   retrieval is not LangChain, so `hybrid_retrieve` records a typed `retriever` observation (`retrieve-passages`) with
   the query in and chunk ids, scores and a bounded text excerpt out.
3. **Redaction before export.** `mask_otel_spans` runs on every exported span batch and replaces secret-named keys
   (`raw_token`, `authorization`, `api_key`, ...) and credential-shaped text (JWTs, bearer values, provider keys)
   with `[REDACTED]`. The same `redact` function is the `hide_inputs/outputs/metadata` hook of the LangSmith client, so
   LangSmith tracing, when enabled, gets the same protection.
4. **Off costs nothing and never blocks startup.** `LANGFUSE_TRACING=false` (default) imports no SDK and adds no
   callbacks. Switched on with a key missing it logs a warning and stays off. `LANGFUSE_PUBLIC_KEY` and
   `LANGFUSE_SECRET_KEY` default to empty (the permitted optional-key default), `LANGFUSE_BASE_URL` and
   `LANGFUSE_SAMPLE_RATE` are required settings, and the secret key is masked in `repr` and JSON. The client is
   flushed and closed in the app lifespan, off the event loop.
5. **Privacy is an explicit choice.** Conversation text and retrieved passages are exported, so the region and project
   are the operator's decision (`.env.example` lists the EU, US, JP and HIPAA regions). The tenant is never a tag.

## Audit against the Langfuse best practices (2026-11-10, live)
Run against the HIPAA region with the branch code: trace shape, names, root input/output, session, user, environment,
model name and token usage are present; a scan of the exported data found no JWT or provider key and `raw_token` shows
`[REDACTED]`. Known limits, accepted: LangChain internals (`RunnableSequence`, `_check_refusal`) appear as spans, and
`retrieve-passages` sits next to the graph under the root rather than inside the `hybrid_retrieve` node because our code
runs outside LangChain's run context. Langfuse's v1 trace and observation read endpoints are removed on 2026-11-16;
read data with `GET /api/public/v2/observations`.

## Sources
- https://langfuse.com/docs/observability/best-practices
- https://langfuse.com/integrations/frameworks/langchain
- https://langfuse.com/docs/observability/features/masking
- https://langfuse.com/docs/observability/sdk/instrumentation
