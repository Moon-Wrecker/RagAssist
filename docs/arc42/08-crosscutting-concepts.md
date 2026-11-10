# arc42 section 8: Crosscutting concepts

Status: covers caching, HTTP caching and shared counters (ADR 0015). Other concepts (tenancy, security, events, tracing) are described in their ADRs.

## Caching

```
 request ─> guard / router ──> VerdictCache ────────┐
            hybrid_retrieve ──> RetrievalResultCache ├─> CacheService ──> Cache port ──> in-memory LRU+TTL (default)
 query / chunk embedding ───> EmbeddingService ─────┘      │  keys, codecs,                └> Redis (optional profile)
                                                          │  corpus version, counters
 document.changed (events bus) ──> observer ──────────────┘
```

- **One rule:** every key holds the tenant (and role where results depend on it) and a keyed hash of normalised text,
  never the text; every entry has a TTL; the store is bounded; a hit cannot cross a tenant or role. Built by
  `platform/cache/keys.py`, tested in `tests/security/test_cache_isolation.py`.
- **Invalidation:** the per-tenant corpus version token changes on `document.changed`; the events bus already carries
  that signal from the API and from the worker to every API process.
- **Failure:** a cache backend error is a miss, counted on `/metrics`; the application never fails because of the cache.
- **Switch:** `CACHE_ENABLED=false` restores the exact previous behaviour; `CACHE_BACKEND=redis` shares the cache
  between processes (deployment: `docs/arc42/07-deployment-view.md`, compose profile `redis`).
- **Provider side:** the generator prompt starts with a fixed system message so OpenAI and Gemini implicit prompt
  caching can match the prefix; cached input tokens are recorded.
- **HTTP caching:** `ETag` plus `private` cache headers on `GET /v1/chunks/{id}` (`max-age`) and `GET /v1/documents`
  (`no-cache`, revalidate), `304` only after authorisation; `Cache-Control: no-store` on `/v1/auth/*` and `/v1/events`
  (`shared/http_cache.py`, `NoStoreMiddleware`). Contract: `docs/api/sse-contract.md`.
- **Shared counters:** with `CACHE_BACKEND=redis` the sign-in throttle and the rate limiter count in Redis so limits hold
  across API replicas (`shared/counters.py` port, `platform/cache/counters.py` adapter); an unreachable Redis falls back to
  the per-process counters. The event-stream cap stays per process.
