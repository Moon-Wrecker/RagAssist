# ADR 0015: Caching: a Bounded Port, Tenant-Scoped Keys, Short TTLs and Invalidation by Document Change

## Context & Problem
There was no real cache. One assistant turn makes about six model calls (safety, routing, a complexity score, one
relevance grade per passage, generation, grounding) plus a query embedding, a hybrid search and a rerank, and none of
it was reused: the same question asked twice cost the same twice, and re-indexing an unchanged document embedded every
chunk again. The sign-in throttle, the rate limiter and the event-stream cap were per process.

The system is multi-tenant, so the risk of a cache is not staleness but **a hit that crosses a tenant or a role**. The
design starts from that rule and adds speed only where it can keep it.

## Decision

### The rule (enforced by construction and by tests)
Every key contains the `tenant_id`, and the role where the result depends on who asks. Its variable part is a keyed
hash (HMAC-SHA256, key derived from `SECRET_KEY`) of the **normalised** text (NFKC, case-folded, whitespace collapsed),
never the text, a token or personal data. Every entry has a TTL and the store is bounded. A document upload, re-index
or delete purges the tenant's retrieval entries. `CacheKeyBuilder.key` takes `tenant_id` as a required argument and
raises on a missing or malformed one, so a tenant-less key cannot be built. `tests/security/test_cache_isolation.py`
proves: no cross-tenant hit, no cross-role hit, keys never contain text, and the real upload, re-index and delete
endpoints purge only the caller's tenant.

### Port and adapters (`platform/cache`)
`Cache` port: `get`, `set` (TTL mandatory), `delete`, `delete_prefix`, an atomic `incr` window counter, `stats`.
Values are bytes; `CacheService` owns the JSON and float32 codecs and turns any backend failure into a miss (a cache is
an optimisation, never a reason for an error). Adapters:
- **In-memory LRU+TTL** (default): bounded by `CACHE_MAX_ENTRIES` and `CACHE_MAX_VALUE_BYTES`, expired entries are dropped
  before live ones are evicted. Per process.
- **Redis** (optional, `CACHE_BACKEND=redis`): redis-py `redis.asyncio`, `SET ... EX`, `SCAN` + `UNLINK` for prefix
  purges (never `KEYS`). The password is `CACHE_REDIS_PASSWORD`; the URL must not carry credentials (a validator rejects
  it). Redis failures count in `/metrics` and behave as misses.
- **Null** when `CACHE_ENABLED=false`: behaviour is identical to the code before this ADR.

### What is cached
| What | Key (after tenant, always) | TTL | Notes |
|---|---|---|---|
| Query embedding | role-less; hash(text) + provider, model, dimension | `CACHE_EMBEDDING_QUERY_TTL_SECONDS` (1 h) | Only vectors from the chain's **first** provider are stored: a fallback provider's vector is returned but never cached, so a stored vector always matches the stored corpus. |
| Chunk embedding (ingestion, re-index) | hash(embed text) + provider, model, dimension | `CACHE_EMBEDDING_DOCUMENT_TTL_SECONDS` (24 h) | A chunk whose content hash already has a vector is not sent to the provider again. Worker-local with the memory backend, shared with Redis. |
| Retrieval result (`Hit` list, before rerank) | role, hash(query), k, **corpus version** | `CACHE_RETRIEVAL_TTL_SECONDS` (60 s) | Empty and degraded results (one of dense/sparse failed) are not stored. |
| Safety verdict | role, hash(question), decider chain config | `CACHE_DECISION_TTL_SECONDS` (5 min) | **Only real verdicts.** The fail-closed "check did not run" result (`provider_used=fallback_default`, `safety_check_error`) is never stored. |
| Router verdict + complexity | role, hash(question), router chain config | same | A defaulted route (`fallback_default`) or a failed complexity score is never stored. |

**Not cached, deliberately:** answers (no semantic or near-duplicate caching; it needs its own review), relevance
grades and grounding checks (they depend on passage text and the generated answer), reranking, account tools and
anything involving approval or escalation.

### Corpus version and invalidation
Each tenant has a *corpus version*: a random token stored in the cache and mixed into every retrieval key, combined
with a version for shared knowledge (rows with no tenant). `document.changed` on the events bus (ADR 0008) replaces
the token and deletes the tenant's retrieval entries by prefix. The event already exists on every path that changes a
corpus: the API publishes it on upload, re-index and delete, and the ingestion worker publishes it after the new chunks
are committed (`pg_notify`, heard by every API process). Each API process attaches an observer to its event hub, so
no second channel exists. A search that was in flight when the document changed stored its result under the *old*
token, which nobody asks for any more. If the token itself is evicted or expires, a *new random* token is minted, which
can only cause misses: an old entry can never become valid again. Shared-knowledge changes (written by the `seed`
command, which publishes no event) are bounded by the retrieval TTL unless Redis is shared and the token is bumped.

### Provider prompt caching
The generator prompt is now a fixed system message first (two constants, no placeholders) and the passages and question
after it, so the part that never changes is the prefix OpenAI and Gemini cache implicitly. Anthropic's explicit
`cache_control` was **not** added: caching needs a prefix of at least 1024 tokens (2048 for some models) and ours is
about 60, so the marker would only add the 25% cache-write surcharge. Revisit if the system prompt or tool schemas grow
past the minimum. Cached input tokens are summed from `usage_metadata.input_token_details.cache_read` per generation,
counted in `ragassist_llm_input_tokens_total{cached}` and logged; Langfuse shows the same numbers from the callback
handler. Providers that do not stream usage (some OpenAI-compatible endpoints) record nothing rather than zero.

### Observability
`/metrics` (admin only) exports `ragassist_cache_requests_total{kind,result}`, `..._evictions_total`,
`..._expirations_total`, `..._rejected_total`, `..._errors_total` and `ragassist_cache_entries`; labels are the kind
of entry and the backend, never a tenant or key. The `check-safety`, `route-question` and `retrieve-passages` Langfuse
observations carry `cache_hit=true|false`, so a trace shows which steps were skipped.

## Measured effect (scripted models, in-memory cache; `tests/graph/test_graph_cache.py`)
A repeated question, second ask, same tenant and role: **6 model calls become 3** (safety, routing and the complexity
score are skipped; grading, generation and grounding still run) and **2 searches become 1** (the second search, and its
query embedding, come from the cache). The first ask costs the same with the cache on or off.

## Security notes
- Values (passages, vectors) are tenant data. With Redis the instance must be private to the deployment: compose network
  or a firewalled host, a password, `rediss://` across hosts. The compose service publishes no host port.
- Keyed hashing means reading the keys does not reveal short questions by dictionary guessing; a rotated `SECRET_KEY`
  starts a new key space (a cold cache, no leakage).
- Normalisation merges "Reset  my PASSWORD" and "reset my password" into one entry, including their query embedding.

## Consequences
- With the memory backend each API process and the worker have their own cache; Redis shares them.
- `CACHE_*` settings are required (no code defaults, `.env.example` documents them); only `CACHE_REDIS_URL` and
  `CACHE_REDIS_PASSWORD` may be empty. Existing `.env` files need the new block (`ragassist init-env` writes it).
- The `redis` Python package is a hard dependency (exact pin `redis==8.1.0`: MIT, maintained by Redis Inc., about 200
  million downloads a month) but only imported when `CACHE_BACKEND=redis`.
- Compose has an optional `redis` service behind the `redis` profile (off by default): official image from Docker Hub,
  pinned `redis:8.2.11-alpine`, password from `.env` (the container refuses to start without one), `allkeys-lru`, no
  persistence, no published port. Redis 8 is available under AGPLv3 (and RSALv2/SSPL); running it unmodified as a
  separate service places no obligation on this code. Use the BSD-licensed 7.2 line or Valkey if that matters to you.

## Suggested frontend changes (not made here)
Set `staleTime` per query class instead of the single 30 s: conversation list and messages 0 (events invalidate them),
document list 30 s (`document.changed` invalidates), team members 60 s, a citation passage `Infinity` for the session
(a chunk id is immutable; use the new `ETag`), and prefetch `GET /v1/chunks/{id}` on hover or focus of a citation marker.

## Sources
- redis-py docs and package metadata: https://redis.readthedocs.io/en/latest/ , https://pypi.org/project/redis/ ,
  https://github.com/redis/redis-py (MIT)
- Redis `SCAN`, `UNLINK`, `SET EX`, eviction policies: https://redis.io/docs/latest/commands/scan/ ,
  https://redis.io/docs/latest/develop/reference/eviction/
- Docker Hub official `redis` image tags: https://hub.docker.com/_/redis
- OpenAI prompt caching (prefix match, 1024-token minimum, automatic):
  https://platform.openai.com/docs/guides/prompt-caching
- Gemini implicit caching: https://ai.google.dev/gemini-api/docs/caching
- Anthropic prompt caching (`cache_control`, minimum cacheable length, write surcharge):
  https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Python `hmac`, `unicodedata`; OWASP guidance on keeping sensitive data out of cache keys.
- Existing designs reused: ADR 0008 (`document.changed`, ids only), ADR 0002 (tenant context), `LoginThrottle` (bounded
  table).
