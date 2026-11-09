# ADR 0008: Live Events over LISTEN/NOTIFY, Human Handoff and Turns That Outlive the Request

## Context & Problem
The web UI needs to learn about changes it did not cause: a document finishing indexing in the worker, an agent
reply arriving in a customer's thread, a new escalation appearing in the inbox. It also needs three behaviours the
API did not have: opening the passage behind a citation, a defined result when a human agent owns a conversation,
and a Stop button that does not lose the turn.

## Decision
1. **A change-notification stream, `GET /v1/events` (SSE).** Events carry **only a type and ids**, never content.
   The client refetches through the normal API, which enforces tenant, owner and role again, so a leaked or forged
   notification exposes nothing. `Event` rejects any payload key that is not an id field, and a malformed payload read
   from the channel is dropped.
2. **PostgreSQL `LISTEN`/`NOTIFY` as the bus.** The database is already shared by the API and the worker, so no broker
   is added. `pg_notify` is transactional: published inside `ScopedDatabase.transaction()` it is delivered only after
   the commit (a refetch always sees committed rows), after a rollback it is never delivered. The worker publishes
   through the same table-less call. Port: `platform/events/ports.py`; adapters: PostgreSQL and in-memory (memory
   backend and tests).
3. **One listener connection per API process.** A dedicated psycopg connection (the SQLAlchemy/asyncpg pool is not used
   because a pooled connection cannot hold a `LISTEN`) fans events out to the in-process `EventHub`. It probes with
   `SELECT 1` every 30 seconds, and a lost connection is re-opened with exponential backoff. Notifications sent while
   it was away are gone, so every reconnect sends `resync` to all streams.
4. **Bounded per-subscriber queues.** Each stream has a queue of `EVENTS_QUEUE_SIZE` events. A slow client that
   overflows it gets the queue dropped and one `resync` (refetch everything) instead of unbounded memory or a blocked
   fan-out.
5. **Server-side audience filter.** Tenant first, then the audience of the event: `admins` (job and document events),
   `staff` (escalation inbox), `owner_and_staff` (conversation events; an event without a known owner reaches staff
   only). Identity comes from the verified JWT only.
6. **Token lifetime and connection cap.** The stream ends with `reauth` at the access token's expiry; the client
   refreshes and reconnects. A user may hold `EVENTS_MAX_STREAMS_PER_USER` streams per API process; more answer
   `429`. The path is exempt from `RateLimitMiddleware` (one long request per tab, bounded by the cap instead).
7. **Middleware.** `BaseHTTPMiddleware` (rate limit, timing) was checked with a hand-driven ASGI client: frames are
   flushed while the stream is open and a disconnect reaches the endpoint, so they were kept. One real defect was
   found and fixed: the timing middleware raised `UnboundLocalError` when a request was cancelled; cancellations are
   now recorded as status `499`.
8. **`GET /v1/chunks/{chunk_id}`.** A retrieval application facade (`GetChunk` over a `ChunkReader` port) returns the
   passage text and provenance for the caller's tenant plus global rows; other tenants' chunks and unknown ids are both
   `404`. The query repeats the tenant filter that row-level security enforces.
9. **Human handoff.** While a conversation is `escalated`, `POST .../messages` saves the customer message, does not
   run the graph, and answers with the handoff (SSE: `escalated` with the open ticket, then `done` with status
   `escalated`; JSON: empty answer, route `human_handoff`, status `escalated`). Resolving sets `resolved`, so the next
   message goes to the assistant; a later escalation opens a **new** ticket (the idempotency of escalation now only
   applies while the conversation is escalated).
10. **Turns outlive the request.** The graph run, the saving of the answer and the ticket creation run in a task owned
    by `assistant/application/turns.py`, not in the request. A client that disconnects (Stop) cannot cancel it: the
    answer is saved, the ticket opened and `message.created` published, and the client refetches the conversation.
    `asyncio.shield` alone was not enough for streaming, because Starlette cancels the response at an arbitrary
    `yield` and the code after it never runs. The JSON path and the approval resume use the same helper with
    `shield`. Shutdown waits for in-flight turns (`drain`) before the pools close.

## Consequences
- **Positive:** live UI without polling or a new service; no content in the channel; isolation checked in the
  database, the filter and the refetch; a stopped or dropped turn is never lost.
- **Negative:** events are not replayed (clients invalidate everything after a reconnect); a stopped turn keeps
  running and spends its tokens; the connection cap and the listener are per process, so replicas each hold one
  listener connection and one cap; psycopg's async mode needs the selector event loop on Windows (as the checkpointer).
- **Operational:** new settings `EVENTS_MAX_STREAMS_PER_USER` and `EVENTS_QUEUE_SIZE` (in `.env.example`). Behind
  nginx the stream needs buffering off (`X-Accel-Buffering: no` is sent) and a read timeout above the 15 second ping.

## Consulted
PostgreSQL `NOTIFY`/`LISTEN` documentation (transactional delivery, 8000 byte payload, per-channel semantics);
psycopg 3 "Asynchronous notifications" (`AsyncConnection.notifies(timeout=...)`); WHATWG Server-Sent Events
specification; Starlette `StreamingResponse` and `BaseHTTPMiddleware` documentation and the disconnect behaviour
checked empirically in `tests/unit/platform/events/test_events_api.py`; Python `asyncio` documentation (`create_task`
holds only a weak reference, `shield`); the existing `docs/api/sse-contract.md`.
