# Glossary

**Type:** Reference · **Audience:** everyone who reads or writes RagAssist documentation · **Verified against:** `a989287`

**In plain English:** This page gives one meaning to each project term. All other pages use these words in this sense.
Look up a word here when a page uses it and you do not know it.

Terms are in alphabetical order. The last column shows where the term lives in the code or in the documents. A path in
backticks is a file in the repository. A link goes to a page in this documentation.

## How to use this page

- Search for the term with your browser (Ctrl+F or Cmd+F).
- Follow the link in the last column when you want the full story.
- When you add a new project term to any page, add it here in the same change. Keep the table in alphabetical order.
- Use the same word for the same thing. For example, write "workspace" for the customer-facing name of a tenant, and
  "tenant" only when you talk about the data and the database.

## Terms

| Term | Plain definition | Where it appears |
|---|---|---|
| **Access token** | A short-lived signed JWT. The browser keeps it in memory and sends it in the `Authorization` header. The lifetime comes from `AUTH_ACCESS_TOKEN_MINUTES`. | `src/ragassist/modules/identity/application/auth_service.py`; [accounts, sessions and tokens](explanation/accounts-sessions-and-tokens.md) |
| **Account agent** | The graph node that lets a model call action tools for the customer account. It is the only node that can pause for approval. | `src/ragassist/modules/assistant/graph/nodes/account_agent_node.py` |
| **Action tool** | A function that the assistant can call on a customer account, for example `list_invoices` or `update_billing_email`. A tool is a read tool or a write tool. | `src/ragassist/modules/actions/tools/__init__.py`; [approvals and actions](explanation/approvals-and-actions.md) |
| **Admin** | A role. An admin manages the team, the knowledge base and the settings of one workspace. An admin can also read every conversation of the workspace and decide on approvals. | `UserRole.ADMIN` in `src/ragassist/shared/security/jwt.py` |
| **Agent (support agent)** | A role. An agent works in the inbox, reads conversations of the workspace and replies to escalated customers. Do not confuse it with the "account agent" node of the graph. | `UserRole.AGENT`; `src/ragassist/modules/escalation/application/__init__.py` |
| **Alembic** | The tool that applies database migrations. The command `ragassist db upgrade` runs it. | `migrations/`; `src/ragassist/cli/ops.py` |
| **Application role (`app_user`)** | The database role that the API and the worker use. It is not a superuser, does not own the tables and cannot bypass row-level security. The name comes from `DB_APP_USER`. | `infra/postgres/create-app-role.sh`; [ADR 0002](adr/0002-row-level-security.md) |
| **Approval** | The decision of a person to allow or refuse a write action. The decision is bound to the pending interrupt of one conversation. | `decide_action` in `src/ragassist/modules/assistant/api/router.py`; [ADR 0006](adr/0006-conversation-access-and-approval-binding.md) |
| **Argon2id** | The password hashing method. The code uses the `argon2-cffi` library with its default settings. | `src/ragassist/modules/identity/adapters/argon2_hasher.py`; [ADR 0007](adr/0007-accounts-and-sessions.md) |
| **ASD-STE100** | Simplified Technical English. It is a writing standard with short rules for words and sentences. This project writes in the style of it, without a claim of certification. | [writing style](contributing/writing-style.md) |
| **Assistant graph** | The LangGraph state machine that turns a question into an answer. It has 11 nodes. | `src/ragassist/modules/assistant/graph/builder.py`; [how an answer is made](explanation/how-an-answer-is-made.md) |
| **Assistant module** | The bounded context for conversations, the graph and the streaming API. | `src/ragassist/modules/assistant/` |
| **Audience (of an event)** | The group of users inside one tenant who may receive a live event: `admins`, `staff` or `owner_and_staff`. | `Audience` in `src/ragassist/platform/events/model.py` |
| **Audit log** | The table `tool_audit_log`. The runtime writes one row for each tool execution, with the status and the arguments. | `migrations/versions/0001_initial_schema.py`; `build_tool_registry` in `src/ragassist/runtime.py` |
| **Backoff** | A growing wait between two attempts. The web app uses exponential backoff with jitter to reconnect the live event stream. | `frontend/src/events/event-stream.ts` |
| **Bounded context** | A part of the system with its own language and its own data. In the code it is a vertical module in `src/ragassist/modules/`. | [why a modular monolith](explanation/why-a-modular-monolith.md) |
| **Bounded executor** | A thread pool with 4 workers. CPU-bound work runs there so that it does not block the event loop. | `run_cpu_bound` in `src/ragassist/shared/resilience.py` |
| **Brightness budget** | A limit on how bright the liquid background may become. A test checks the text contrast against the worst case that the budget allows. | `frontend/src/background/liquid-config.ts`; [the web app and design system](explanation/the-web-app-and-design-system.md) |
| **C4 model** | A way to draw architecture at four zoom levels: context, container, component and code. | `docs/c4/`; [writing style](contributing/writing-style.md) |
| **Cache** | A short-lived store for results that are costly to compute. The default backend is in memory. The optional backend is Redis. | `src/ragassist/platform/cache/`; [ADR 0015](adr/0015-caching.md) |
| **Cache key** | The text that names a cache entry. Every key holds the tenant id. The variable part is a keyed hash of the normalised text. | `CacheKeyBuilder` in `src/ragassist/platform/cache/keys.py` |
| **Canary** | A unique marker string that a security test plants in the data of one tenant. The leak gate looks for it in what another tenant can see. | `tests/security/test_leak_gate.py`; [testing strategy](explanation/testing-strategy.md) |
| **Checkpoint** | A saved copy of the graph state. LangGraph writes it to PostgreSQL. A paused approval waits in a checkpoint. | `build_checkpointer` in `src/ragassist/runtime.py` |
| **Checkpointer** | The LangGraph component that reads and writes checkpoints. The project uses `AsyncPostgresSaver`. | `src/ragassist/runtime.py` |
| **Choice question** | A question for a decider with a fixed list of answers. The router uses one to choose a route. | `ChoiceQuestion` in `src/ragassist/platform/decisions/ports.py` |
| **Chunk** | A part of a document, about 512 tokens at most. A chunk has text, a vector and a keyword index entry. Retrieval returns chunks. | `src/ragassist/modules/knowledge/domain/__init__.py`; [retrieval and chunking](explanation/retrieval-and-chunking.md) |
| **Chunker** | The component that cuts a parsed document into chunks. The default is the `HybridChunker`. | `src/ragassist/modules/knowledge/adapters/chunkers/` |
| **Citation** | A reference from an answer to the chunk that supports it. It has the chunk id, the document id, the title, the page and the heading path. | `Citation` in `src/ragassist/modules/assistant/graph/state.py`; [SSE contract](api/sse-contract.md) |
| **Complexity** | A score for the difficulty of a question. The generate node uses it to choose a model tier. | `router_node.py`; `generate_node.py` in `src/ragassist/modules/assistant/graph/nodes/` |
| **Confidence gate** | A rule that refuses a decider answer when its confidence is below `DECIDER_MIN_CONFIDENCE`. The chain then asks the next decider. Only the routing question uses it. | `_execute_with_confidence` in `src/ragassist/platform/decisions/service.py` |
| **Contextual header** | The text `[Document: ... \| Section: ...]` that the chunker puts before the text it embeds. The stored text for citations stays clean. | `context_pass` in `src/ragassist/modules/knowledge/adapters/chunkers/passes.py`; [ADR 0003](adr/0003-hybrid-chunking.md) |
| **Contract suite** | One shared set of tests for a port. Every adapter and every fake must pass it, so a fake cannot drift from the real adapter. | `tests/support/contracts/`; [testing strategy](explanation/testing-strategy.md) |
| **Conversation** | A thread of messages between one user and the assistant. It has a status: `open`, `escalated` or `resolved`. | `conversations` table; `src/ragassist/modules/assistant/` |
| **Corpus version** | A random token for the documents of one tenant. The retrieval cache puts it in every key. A document change replaces it. | [ADR 0015](adr/0015-caching.md) |
| **Credential masking** | Replacement of secret-looking text with `[REDACTED]` before data goes to a trace. It does not remove personal data or conversation text. | `src/ragassist/shared/observability/`; [observability and privacy](explanation/observability-and-privacy.md) |
| **Cross-encoder** | A model that reads the question and a passage together and gives a relevance score. It is the first member of the default reranker chain. | `src/ragassist/platform/rerank/adapters/cross_encoder_adapter.py` |
| **CSP (content security policy)** | A browser header that limits what a page can load or run. The web container sends a strict one, except `style-src` allows inline styles. | `infra/nginx/templates/security-headers.inc.template`; [ADR 0014](adr/0014-web-delivery.md) |
| **Decider** | A component that answers a typed question (a choice, a yes-or-no or a score) and gives a probability. Several adapters implement the port. | `src/ragassist/platform/decisions/ports.py`; [the decision layer](explanation/the-decision-layer.md) |
| **Decider chain** | The ordered list of deciders for the safety check, the grader and the grounding check. The setting is `DECIDER_CHAIN`. Routing has its own list, `ROUTER_DECIDER_CHAIN`. The code registers one model decider for each model, named `llm_structured`, `llm_structured_2` and `llm_structured_3`. | `build_decision_service` in `src/ragassist/platform/decisions/service.py` |
| **Decision layer** | The set of deciders and the service that uses them. It answers routing, safety, relevance and grounding questions without text generation. | [ADR 0004](adr/0004-decision-layer.md) |
| **Defect registry** | The list `DEFECTS` in the test support code. A test for a known bug carries a strict expected-failure marker with an id from this list. The list is empty at this commit. | `tests/support/defects.py`; [testing strategy](explanation/testing-strategy.md) |
| **Detached turn** | A turn that runs in its own task, not in the HTTP request. The turn finishes even when the client disconnects. | `src/ragassist/modules/assistant/application/turns.py`; [ADR 0008](adr/0008-live-events-handoff-and-detached-turns.md) |
| **Dev token** | A token that a command or an endpoint makes for local work. Its life comes from `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`. Browser sign-in uses other settings. | [accounts, sessions and tokens](explanation/accounts-sessions-and-tokens.md) |
| **Diataxis** | A method that splits documentation into tutorials, how-to guides, reference and explanation. | [writing style](contributing/writing-style.md) |
| **Dimension (of an embedding)** | The length of an embedding vector. The setting is `EMBEDDING_DIMENSION` and the database column is `vector(1536)`. | `migrations/versions/0001_initial_schema.py`; `src/ragassist/platform/embeddings/projector.py` |
| **Dimension projection** | The step that pads or cuts an embedding from a fallback model to the column size and then normalises it. The result lives in a different vector space than the stored vectors. | `DimensionProjector`; [retrieval and chunking](explanation/retrieval-and-chunking.md) |
| **Document** | A file that an admin uploads to the knowledge base. The allowed types are PDF, Markdown, HTML and CSV. The size limit is 50 MiB. | `src/ragassist/modules/knowledge/` |
| **Domain layer** | The inner layer of a module. It holds pure Python rules and value objects. It does not import frameworks. | [why a modular monolith](explanation/why-a-modular-monolith.md) |
| **Embedding** | A list of numbers that represents the meaning of a text. Similar texts have similar vectors. | `src/ragassist/platform/embeddings/` |
| **Embed text** | The text of a chunk with its contextual header. The embedding comes from this text. The stored raw text is used for citations and keyword search. | [retrieval and chunking](explanation/retrieval-and-chunking.md) |
| **Escalation** | The handoff of a conversation to a human agent. It opens a helpdesk ticket and sets the status `escalated`. | `src/ragassist/modules/escalation/`; [human handoff and live events](explanation/human-handoff-and-live-events.md) |
| **ETag** | An HTTP header with a hash of a response body. The browser sends it back in `If-None-Match`. The API then answers `304` when nothing changed. | `src/ragassist/shared/http_cache.py`; [ADR 0015](adr/0015-caching.md) |
| **Event (live event)** | A change notification with a type and ids only. It never carries content. | `src/ragassist/platform/events/model.py`; [SSE contract](api/sse-contract.md) |
| **Event bus** | The port that publishes live events. The adapters are PostgreSQL and in-memory. | `src/ragassist/platform/events/ports.py` |
| **Event hub** | The in-process component that fans events out to the bounded queues of connected streams. | `src/ragassist/platform/events/hub.py` |
| **Fail closed** | A rule: when a check cannot run, refuse and do not allow. The safety check and the grounding check fail closed. | `src/ragassist/platform/decisions/service.py`; [the decision layer](explanation/the-decision-layer.md) |
| **Fail open** | A rule: when a check cannot run, allow and keep going. The relevance grader fails open, because losing the only source is worse than keeping one extra passage. | [the decision layer](explanation/the-decision-layer.md) |
| **Fake (scripted model)** | A test stand-in for a port. A scripted model returns replies that the test wrote in advance, so a graph test is repeatable. | `tests/fakes/`; [testing strategy](explanation/testing-strategy.md) |
| **Fallback chain** | An ordered list of providers. The code tries the next one when a member fails, times out or gives an unacceptable result. | `FallbackChain` in `src/ragassist/shared/resilience.py` |
| **FlashRank** | A small CPU reranker based on ONNX. It is the second member of the default reranker chain. | `src/ragassist/platform/rerank/adapters/flashrank_adapter.py`; [ADR 0005](adr/0005-reranker-chain.md) |
| **FORCE RLS** | The PostgreSQL setting `FORCE ROW LEVEL SECURITY`. It makes the policies apply to the table owner as well. | `migrations/versions/0001_initial_schema.py`; [ADR 0002](adr/0002-row-level-security.md) |
| **Fragment link** | A link whose secret is after the `#`. Browsers never send the fragment to a server. Invite and reset links use it. | `frontend/src/auth/fragment-token.ts`; [ADR 0007](adr/0007-accounts-and-sessions.md) |
| **Frame (SSE frame)** | One message on a server-sent event stream: an `event:` line, a `data:` line and a blank line. | `src/ragassist/shared/sse.py`; [SSE contract](api/sse-contract.md) |
| **Frame batcher** | Browser code that collects stream tokens and applies them once for each animation frame. | `frontend/src/features/chat/`; [the web app and design system](explanation/the-web-app-and-design-system.md) |
| **Generator** | The model role that writes the answer. The role has a primary model and fallbacks in `config/models.yaml`. | `config/models.yaml`; `generate_node.py` |
| **Glass (design)** | The surface style of the web app. A glass surface is translucent and blurred. There are three thicknesses: thin, regular and thick. | `frontend/src/index.css`; [ADR 0016](adr/0016-liquid-redesign.md) |
| **Grader (relevance grader)** | The step that asks a decider if one retrieved chunk helps to answer the question. | `grade_relevance_node.py`; `grade_chunk_relevance` in `service.py` |
| **Grounding check** | The step that asks a decider if every claim in the answer is supported by the cited chunks. | `verify_grounding_node.py`; `judge_grounding` in `service.py` |
| **Guard (input guard)** | The first node of the graph. It runs the safety check on the question and stops the turn when the check refuses. | `src/ragassist/modules/assistant/graph/nodes/guard_node.py` |
| **Handoff** | The state in which a human agent owns a conversation. The assistant stays silent until an agent resolves it. | `ask_message` in `src/ragassist/modules/assistant/api/router.py`; [ADR 0008](adr/0008-live-events-handoff-and-detached-turns.md) |
| **Hexagonal architecture** | A layout where the core logic does not depend on frameworks. The core talks to the outside through ports. Adapters implement the ports. | [why a modular monolith](explanation/why-a-modular-monolith.md) |
| **HNSW** | A type of vector index in pgvector. The table `chunks` has an HNSW index with cosine distance. | `migrations/versions/0001_initial_schema.py` |
| **Hybrid search** | A search that runs a vector search and a keyword search, then joins both rankings with RRF. | `HybridRetriever` in `src/ragassist/modules/retrieval/fusion.py`; [retrieval and chunking](explanation/retrieval-and-chunking.md) |
| **Hygiene test** | A test about the repository and not about behaviour, for example a check that `.env.example` matches the settings. | `tests/hygiene/`; [testing strategy](explanation/testing-strategy.md) |
| **Idempotent** | A property of an action: running it twice has the same effect as running it once. The ingestion worker and the escalation use case are idempotent. | `ProcessIngestionJob`; `EscalateConversation` |
| **Inbox** | The web page where agents and admins see escalated conversations and reply. | `frontend/src/features/inbox/`; [ADR 0011](adr/0011-admin-screens.md) |
| **Ingestion job** | A row in `ingestion_jobs` that tracks the processing of one uploaded document. | `src/ragassist/modules/knowledge/application/ingestion_service.py` |
| **Interrupt** | A pause of the graph that waits for a human decision. The account agent node raises it before a write action. | `langgraph.types.interrupt` in `account_agent_node.py` |
| **Interrupt id** | The id of the interrupt that a checkpoint is paused on. A decision must name it, or the API answers `409`. | `_pending_interrupt` in `router.py` |
| **Invite** | A one-time link that lets a new person set a password. An admin creates it and hands it over. There is no email service. | `src/ragassist/modules/identity/api/team_router.py`; [ADR 0007](adr/0007-accounts-and-sessions.md) |
| **JWT (JSON Web Token)** | A signed token with claims. RagAssist uses it as the access token. The claims are `sub`, `tenant_id`, `role`, `exp` and `iat`. | `src/ragassist/shared/security/jwt.py` |
| **Knowledge base** | All documents and chunks of one workspace. The web page for it is "Knowledge". | `frontend/src/features/knowledge/` |
| **Knowledge module** | The bounded context for upload, parsing, chunking, embedding and indexing. | `src/ragassist/modules/knowledge/` |
| **Langfuse** | A tracing service. It shows one trace for each assistant turn. Tracing is off by default. | `src/ragassist/shared/observability/tracing.py`; [ADR 0012](adr/0012-langfuse-tracing.md) |
| **LangGraph** | The library that runs the assistant as a graph of nodes with checkpoints and interrupts. | `src/ragassist/modules/assistant/graph/` |
| **Leak gate** | A security test that plants canaries in tenant A, reads everything tenant B can see and fails on any hit. The target is zero. | `tests/security/test_leak_gate.py`; [testing strategy](explanation/testing-strategy.md) |
| **Liquid background** | The moving monochrome picture behind the web app. A shader draws it on a canvas. | `frontend/src/background/`; [ADR 0016](adr/0016-liquid-redesign.md) |
| **LISTEN/NOTIFY** | The PostgreSQL feature for messages between connections. The live event bus uses it. | `src/ragassist/platform/events/adapters/postgres.py` |
| **Live test** | A test that calls a real provider. It runs only with `--run-live` and `RAGASSIST_LIVE_*` settings. | `tests/live/`; [testing strategy](explanation/testing-strategy.md) |
| **LocalStack** | A local stand-in for AWS services. The stack uses it for S3, SQS and Secrets Manager. | `compose.yaml`; `infra/localstack/init.sh` |
| **Message** | One entry in a conversation. The role of a message is `user`, `assistant` or `agent`. | `messages` table |
| **Mock SaaS** | A small separate FastAPI service. It stands in for the customer product and the helpdesk. It has demo accounts. | `services/mock_saas/main.py` |
| **`models.yaml`** | The file `config/models.yaml`. It lists providers, models, aliases and roles. It is the one place for model names. | `config/models.yaml`; [provider abstraction and fallbacks](explanation/provider-abstraction-and-fallbacks.md) |
| **Modular monolith** | One deployable application that is split inside into modules with clear borders. | [why a modular monolith](explanation/why-a-modular-monolith.md) |
| **Namespaced thread id** | The graph thread id in the form `{tenant_id}:{conversation_id}`. The prefix keeps checkpoints of two tenants apart. | `ask_message` and `decide_action` in `router.py` |
| **Network guard** | A test fixture in the root `conftest.py` that blocks outbound network calls unless the test has the `network` marker. | `tests/conftest.py`; [testing strategy](explanation/testing-strategy.md) |
| **Node (graph node)** | One step of the assistant graph. Each node reads and writes the graph state. | `NODE_NAMES` in `builder.py` |
| **Observation (Langfuse)** | One step inside a trace, for example `check-safety` or `retrieve-passages`. | `src/ragassist/shared/observability/tracing.py` |
| **Origin check** | A guard on the cookie endpoints. The `Origin` header must match a trusted origin. It adds to `SameSite=Strict`. | `require_trusted_origin` in `src/ragassist/modules/identity/api/deps.py` |
| **Passage** | The text of a chunk, shown to a person when they open a citation. | `GET /v1/chunks/{chunk_id}`; [SSE contract](api/sse-contract.md) |
| **Pending (spec map)** | A requirement in the spec map whose feature is not written yet. With `RAGASSIST_STRICT_PENDING=1`, a pending entry that starts to pass fails the run. | `tests/support/specs/map.py`; [testing strategy](explanation/testing-strategy.md) |
| **pgvector** | The PostgreSQL extension for vector columns and vector indexes. | `migrations/versions/0001_initial_schema.py`; [ADR 0001](adr/0001-pgvector-unified-storage.md) |
| **Platform layer** | The folder `src/ragassist/platform/`. It holds swappable adapters for models, embeddings, rerankers, deciders, storage, queue, events and cache. | `src/ragassist/platform/` |
| **Port** | A Python `Protocol` that describes what the core needs. An adapter implements it. | `ports.py` files under `platform/` and `modules/` |
| **Predicate question** | A yes-or-no question for a decider. It returns a verdict and a probability. | `PredicateQuestion` in `ports.py` |
| **Principal** | The verified identity of the caller: user id, tenant id, role and the raw token. It comes only from the JWT. | `Principal` in `src/ragassist/shared/security/jwt.py` |
| **Prompt injection** | Text that tries to change the instructions of a model. The safety check and the untrusted-context wrapper address it. | `guard_node.py`; `generate_node.py`; [ADR 0004](adr/0004-decision-layer.md) |
| **Provider** | A company or server that supplies models, for example OpenAI, Anthropic, Gemini, OpenRouter or a local server. | `providers:` in `config/models.yaml` |
| **Provider registry** | A map from a provider name to a factory function. The code builds adapters through it. | `ProviderRegistry` in `src/ragassist/shared/registry.py` |
| **Query rewrite** | The `rewrite` node. In this code it only counts the attempts and adds the word "details" to the query on a retry. It makes no model call. | `src/ragassist/modules/assistant/graph/nodes/rewrite_node.py` |
| **Rate limiter** | Middleware that limits the number of requests from one address. | `src/ragassist/shared/security/rate_limiter.py` |
| **Reauth** | A live event. The server sends it when the access token of the stream expires and then closes the stream. The client refreshes the token and reconnects. | `src/ragassist/platform/events/router.py`; [SSE contract](api/sse-contract.md) |
| **Redaction** | The removal of secrets from data before it leaves the process. The function is `redact`. It replaces them with `[REDACTED]`. | `src/ragassist/shared/observability/tracing.py` |
| **Reducer (pure reducer)** | A function that takes the current state and one event and returns the next state, with no side effects. The chat turn uses one. | `frontend/src/features/chat/turn.ts`; [the web app and design system](explanation/the-web-app-and-design-system.md) |
| **Refresh session** | One row in `auth_sessions`. It stands for one refresh token and belongs to a family of tokens from one sign-in. | `migrations/versions/0002_accounts_sessions_invites.py` |
| **Refresh token** | A long-lived opaque token in an `httpOnly` cookie named `ragassist_refresh`. Each use gives a new one. | `src/ragassist/modules/identity/api/deps.py` |
| **Refresh-token family** | All tokens that come from one sign-in by rotation. A replayed old token revokes the whole family. | [accounts, sessions and tokens](explanation/accounts-sessions-and-tokens.md) |
| **Reranker** | A component that reorders retrieved chunks by relevance to the question. | `src/ragassist/platform/rerank/` |
| **Reranker chain** | The ordered list of rerankers with a time limit. The default is `cross_encoder,flashrank,none`. | `RerankerChain`; setting `RERANKER_CHAIN` |
| **Resolve** | The action of an agent or admin that closes an escalation. The status becomes `resolved` and the assistant answers again. | `ResolveEscalation` in `src/ragassist/modules/escalation/application/__init__.py` |
| **Resync** | A live event. It tells the client that events may be lost. The client refetches everything. | `src/ragassist/platform/events/hub.py` |
| **Retrieval** | The step that finds chunks for a question. It combines vector search, keyword search and a reranker. | `src/ragassist/modules/retrieval/` |
| **Reuse detection** | The check that finds a refresh token used a second time. The API then revokes the whole family of tokens. | `AuthService.refresh` in `auth_service.py` |
| **RLS (row-level security)** | A PostgreSQL feature. The database hides rows that do not match a policy. Here the policy compares `tenant_id` with `app.tenant_id`. | `migrations/versions/0001_initial_schema.py`; [ADR 0002](adr/0002-row-level-security.md) |
| **Role** | The permission level of a user in a workspace: `user`, `agent` or `admin`. It is a claim in the JWT. | `UserRole` in `jwt.py` |
| **Role (model role)** | A job name for a model in `models.yaml`: `generator`, `rewriter`, `agent`, `judge` or `decider`. Code asks for a role and not for a model name. | `roles:` in `config/models.yaml` |
| **Role mapping** | The entry in `models.yaml` that gives a model role its primary model, fallbacks, temperature and token limit. | `RoleMappingConfig` in `src/ragassist/platform/llm/catalog_models.py` |
| **Route (assistant route)** | The kind of request that the router finds: `rag_search`, `saas_action`, `general_chat` or `human_escalation`. | `RouteTarget` in `ports.py` |
| **Router** | The node that classifies a question into a route and scores its complexity. | `router_node.py` |
| **RRF (reciprocal rank fusion)** | A method that joins several rankings. A chunk scores `1 / (k + rank)` in each list. The setting `RETRIEVAL_RRF_K` gives `k`. | `src/ragassist/modules/retrieval/domain/__init__.py` |
| **Rules decider** | A decider that uses fixed patterns and needs no network. It is the last member of the default chains. | `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py` |
| **Safety check** | The predicate "does the input contain prompt injection, jailbreak patterns or toxic instructions". The guard node runs it. | `check_safety` in `service.py` |
| **Scoped database** | The helper that opens a session inside a transaction and sets `app.tenant_id` for it. The repositories use it. | `ScopedDatabase` in `src/ragassist/shared/db/scoped.py` |
| **Score question** | A question for a decider that returns a number on ordered levels. The router uses one for complexity. | `ScoreQuestion` in `ports.py` |
| **Secret guard** | The four layers that stop a key from reaching the remote: git hooks, CI, a hygiene test and GitHub push protection. | `scripts/check_secrets.py`; `.githooks/`; [AGENTS.md](../AGENTS.md) |
| **Selfcheck** | A test of the test tools, for example a test that plants a broken adapter to prove that a contract suite fails. | `tests/selfcheck/`; [testing strategy](explanation/testing-strategy.md) |
| **Semantic router** | A decider for routing. In this code it measures word overlap with example sentences for each route. | `semantic_router_adapter.py` |
| **Session (Langfuse)** | A group of traces. RagAssist sets the session id to the conversation id. | `TurnContext` in `tracing.py` |
| **Shared kernel** | The folder `src/ragassist/shared/`. It holds code that every layer may use: settings, security, database helpers and resilience. | `src/ragassist/shared/` |
| **Single-flight refresh** | Browser code that lets only one refresh call run at a time, across tabs, through a Web Lock named `ragassist-refresh`. | `frontend/src/api/http.ts`; [accounts, sessions and tokens](explanation/accounts-sessions-and-tokens.md) |
| **Slug** | The short name of a workspace, for example `demo`. A person types it at sign-in. | `validate_slug` in `src/ragassist/modules/identity/domain/rules.py` |
| **Spec map** | A table in the test support code that links each requirement to its tests and marks entries as pending or drifted. | `tests/support/specs/map.py`; [testing strategy](explanation/testing-strategy.md) |
| **SQS** | The AWS queue service. The API sends an ingestion message and the worker reads it. LocalStack provides it locally. | `src/ragassist/platform/queue/sqs_adapter.py` |
| **SSE (server-sent events)** | A one-way stream of text frames from server to browser over HTTP. | [SSE contract](api/sse-contract.md) |
| **Stop (button)** | The chat control that stops the wait for an answer. The server still finishes the turn and saves it. | [ADR 0008](adr/0008-live-events-handoff-and-detached-turns.md); [ADR 0010](adr/0010-chat-ui.md) |
| **System One decision model** | A model that gives calibrated probabilities for a typed question and does not write text. Jev and OpenAI Decisions are examples. | [ADR 0004](adr/0004-decision-layer.md) |
| **Tenant** | One customer organisation and its data. Row-level security keeps the data of two tenants apart. | `tenants` table; [tenant isolation](explanation/tenant-isolation-defence-in-depth.md) |
| **Test tier** | One group of tests with its own folder, marker and cost: unit, graph, security, integration, end to end, hygiene, selfcheck and live. | `tests/`; [testing strategy](explanation/testing-strategy.md) |
| **Thread id** | The id that LangGraph uses to find the checkpoints of one conversation. See "Namespaced thread id". | `router.py` |
| **Tier (generator tier)** | A group of models for the generate node: `cheap` or `strong`. The complexity score chooses the tier. | `generate_node.py`; `build_runtime` in `runtime.py` |
| **Token counter** | Code that estimates how many tokens a text has. The chunker uses `RegexTokenCounter`, an offline estimate that runs high by about 10 to 20 percent. | `src/ragassist/modules/knowledge/adapters/chunkers/tokenizer.py`; [retrieval and chunking](explanation/retrieval-and-chunking.md) |
| **Trace** | The record of one assistant turn in Langfuse, with nested observations. | [observability and privacy](explanation/observability-and-privacy.md) |
| **TTL (time to live)** | The time after which a cache entry expires. Every cache entry has one. | `CACHE_*_TTL_SECONDS` settings |
| **Turn** | One question from the user and the work that produces the answer, including saving it. | `src/ragassist/modules/assistant/application/turns.py` |
| **Unit of work** | The code block that opens a transaction and sets `app.tenant_id` before any query. | `UnitOfWork` in `src/ragassist/shared/db/uow.py` |
| **User** | A role. A user chats with the assistant and sees only their own conversations. The word also means any person with an account. | `UserRole.USER` |
| **Vertical module** | A module that holds all layers of one feature: domain, application, adapters and API. | `src/ragassist/modules/*` |
| **Viewer** | The identity of the owner of a live event stream, taken from the JWT principal. | `Viewer` in `src/ragassist/platform/events/model.py` |
| **Web app** | The single-page application in `frontend/`. A built copy is served by nginx on the same origin as the API. | `frontend/`; [ADR 0009](adr/0009-web-app.md); [ADR 0014](adr/0014-web-delivery.md) |
| **Worker** | The process that reads ingestion messages from SQS and indexes documents. The command is `ragassist worker`. | `src/ragassist/worker/main.py` |
| **Workspace** | The name that people see for a tenant. A person signs in to a workspace with its slug. | [ADR 0007](adr/0007-accounts-and-sessions.md) |

## Related pages

- [Documentation home](README.md)
- [arc42 section 12, the ten key terms](arc42/12-glossary.md)
- [Writing style](contributing/writing-style.md)
