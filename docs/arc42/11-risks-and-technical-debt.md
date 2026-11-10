# 11. Risks and technical debt

**Type:** Architecture · **Audience:** architects, maintainers, reviewers · **Verified against:** `a989287`

**In plain English:** This page lists what is weak or unfinished in the system today. Each item says what is wrong, why
it matters and what to do. It is honest on purpose. A known gap is safer than a hidden one.

## 11.1 Risks

| ID | Risk | Why it matters | Mitigation or next step |
|---|---|---|---|
| R1 | An access token stays valid after a disable or a role change until it expires (15 minutes by default). `get_current_principal` reads no database row. | A removed user keeps access for a short time. | Keep `AUTH_ACCESS_TOKEN_MINUTES` short. Consider a revocation check for write routes. |
| R2 | The graph sends tenant text to external model providers. | The text leaves the system. | Choose providers by contract. `redact` and `mask_otel_spans` remove credentials from traces, but question and answer text still goes to the trace service when tracing is on. Keep tracing off or choose the trace service by contract. |
| R3 | No multi-factor authentication. No self-service "forgot password". An admin issues each reset link. | A stolen password gives full access to that user. | Plan MFA and a reset flow. |
| R4 | The rate limit of 300 requests in 60 seconds is fixed in the code. The key is `request.client.host`. | Behind a proxy the key is the proxy address unless `TRUSTED_PROXY_IPS` is right. | Move the values to settings. Check `TRUSTED_PROXY_IPS`. |
| R5 | `/docs`, `/redoc` and `/openapi.json` are always on in the API. nginx hides them, but a direct call to the API shows them. | The API surface is public to anyone who reaches the API port. | Add a setting to turn them off in production. |
| R6 | Two refresh calls at the same time can end the session. | A user is signed out. | The web app uses a Web Lock. Keep it. |
| R7 | Compose binds the ports of `localstack` and `mock-saas` without the loopback address. | Both are open to the network on a shared host. | Bind both to the loopback address. |
| R8 | The `api` image copies `seed/`, which is not in git. | Unverified: a clean build can fail. No build was run. | Add the folder or remove the line. |
| R9 | The assistant and escalation modules depend on each other. | A cycle makes change harder. | Move the shared conversation access to a small facade. |
| R10 | The development token needs `DEV_AUTH_SECRET`. The CLI command `ragassist token` has no `APP_ENV` gate. | A token tool is available in any environment. | Add the same gate as the endpoint. |
| R11 | The CSP keeps `style-src 'unsafe-inline'`. | A weaker policy for styles. | See ADR 0014. Revisit when the UI library allows hashes. |
| R12 | The worker never sets `stop_event`. It has no signal handling. | A stop signal ends the process at once. SQS delivers an unfinished message again. | Add signal handling. |
| R13 | A tool token is short-lived, but the audit table holds tool arguments. | Unverified: the content of the arguments in the audit rows was not checked for personal data. | Review the audit content. |

## 11.2 Technical debt in the code

| ID | Item | Detail |
|---|---|---|
| D1 | CPU work on the event loop | The PDF parser calls `fitz` inside `async def parse`. The chunker runs inline. The tokenizer runs inline. `AGENTS.md` section 1.4 requires `run_cpu_bound`. |
| D2 | Missing job stages | The worker never writes the `chunking`, `embedding` or `indexing` statuses. ADR 0011 describes stage text. |
| D3 | Fixed claim timeout | `claim_timeout_seconds` is 240 in the code. It is not a setting. |
| D4 | Memory container uses roles that do not exist | `container.py` asks for `generator_cheap` and `generator_primary`. The call raises `KeyError`. The code falls back to a hard-coded `gpt-4o-mini` and a canned local model. |
| D5 | Hard-coded model in the decider registry | `build_decider_registry` without an `llm_service` uses `gpt-4o-mini`. |
| D6 | Hard-coded demo tenant ids | `cli/ops.py` holds the demo tenant ids of the mock SaaS. |
| D7 | Settings that nothing reads | `DEBUG`, `PROMETHEUS_METRICS_ENABLED`, `WORKER_VISIBILITY_TIMEOUT_SECONDS`, `VECTOR_SEARCH_TOP_K`, `KEYWORD_SEARCH_TOP_K`, `CHUNK_STRATEGY`, `SECRETS_MANAGER_SECRET_NAME` and `ALLOWED_HOSTS`. There is no `TrustedHostMiddleware`. |
| D8 | Dependencies that nothing imports | `slowapi`, `chonkie` and `pymupdf4llm`. ADR 0003 names a chunking library and an exact tokenizer. The code uses `RegexTokenCounter`, an estimate. |
| D9 | Unused helpers | `ensure_thread_access` and `namespaced_thread_id` in `thread_guard.py` are used only by tests. The router builds the thread id inline. |
| D10 | `decision` reranker | `build_reranker_chain` does not know the name `decision`. It skips the name. |
| D11 | `api` reranker settings | The `api` adapter reads `RERANK_API_*` with `getattr`. These are not `Settings` fields. |
| D12 | Duplicate YAML key | `claude-haiku-5-5` has two `pricing` keys in `config/models.yaml`. |
| D13 | Two token life settings | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` sets the development token and `ragassist token`. `AUTH_ACCESS_TOKEN_MINUTES` sets login and refresh. |
| D14 | Fixed retrieval sizes | The retrieve node uses top-k 6. The rerank node uses `min(len, 4)`. The settings `VECTOR_SEARCH_TOP_K` and `KEYWORD_SEARCH_TOP_K` have no effect. |
| D15 | Compose holds deployment values | The shared `x-app` environment fixes `DB_HOST`, `DB_PORT`, `LOCALSTACK_ENDPOINT` and `MOCK_SAAS_BASE_URL`. The file also holds fixed port numbers. This conflicts with the no-hardcoded-values rule. |
| D16 | Only one `import-linter` contract | The contract in `pyproject.toml` is narrow. The real layer rules live in `tests/hygiene/test_architecture.py`. |
| D17 | `docs/testing.md` path | It names the reply path `/replies`. The SSE contract uses `/reply`. Both paths exist in the code. |
| D18 | Comment in `main.py` | The comment calls `NoStoreMiddleware` the outermost. `RequestTimingMiddleware` is. |
| D19 | The `query_dataset` tool | It is a stub that raises "not available yet". |
| D20 | Embeddings in the container | They fail when the OpenAI call fails and the `[ml]` extra is not installed. |
| D21 | Frontend CI | The job is suspended unless `RUN_FRONTEND_CI=true`. |
| D22 | README | The README lists old node names, tools that do not exist, JSON and TXT uploads that the API rejects and 768-dimension embeddings. The code uses 1536. |

## 11.3 Open items for the web app

These items come from `docs/frontend/TODO.md`:

- A smoke run against the real stack.
- A per-user event-stream cap on Redis. Today the cap is per process.
- `staleTime` and prefetch settings for the queries.
- The logo choice. Three concepts exist in `docs/frontend/logo-concepts/`.
- Performance numbers for the new pages and on real devices.
- The refraction and edge-fade effects that the redesign dropped.

The font decision differs between ADR 0009 (Instrument Serif) and ADR 0016 (Geist Serif). `package.json` has
`@fontsource/instrument-serif`. Choose one and update the other ADR.

## 11.4 Data and quality gaps

- The quality numbers for real models are not known. See section [10](10-quality-requirements.md).
- The coverage gate is advisory. The value is below the minimum.
- The web app has no translations. English is the only language.

## 11.5 How to use this page

1. Before you start a change, search this page for the area.
2. When you fix an item, remove it here in the same change.
3. When you find a new gap, add a row with the next ID.
