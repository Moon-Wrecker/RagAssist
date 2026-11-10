# Frontend to-do

One checkbox per planned item, updated in the same PR that does the work. Design brief: React with shadcn/ui, true
monochrome, glass as the primary surface style over a calm monochrome backdrop, no AI slop. Order: backend first, then UI slices, each its own PR.

## Step 0: Prerequisites
- [x] `UnitOfWork` refuses a session that already has a transaction open (PR #11)
- [x] Design tooling installed: `frontend-design` plugin; Vercel `vercel-react-best-practices` and `vercel-composition-patterns` skills (the React Native skills are skipped on purpose)

## Slice 1: Authentication and accounts (backend)
- [x] Migration `0002`: `users.password_hash`, `users.status`, unique `(tenant_id, lower(email))`, `auth_sessions`, `invites` under RLS, slug-lookup policy on `tenants`
- [x] argon2id hashing on the bounded executor
- [x] `POST /v1/auth/login`: generic 401, dummy verification, per-account and per-address throttle
- [x] `POST /v1/auth/refresh` (rotation, replay detection), `POST /v1/auth/logout`, `GET /v1/auth/me`
- [x] `{tenant_id}.{random}` tokens, hash-only storage
- [x] httpOnly, `SameSite=Strict`, path-scoped cookie; `Secure` from settings; `Origin` check on refresh and logout
- [x] Team API (admin only): members, role and status, invites, revoke, reset link; `POST /v1/auth/invites/accept`
- [x] Disabling revokes sessions and pending links
- [x] CLI: `ragassist workspace create`; `seed` prints one set-password link per demo account
- [x] `/v1/auth/token` stays development and test only; `AUTH_*` settings and `WEB_BASE_URL` in `.env.example`; ADR 0007
- [x] Unit, integration (RLS, slug lookup, concurrent claims) and route-sweep tests
- [ ] Live check against Docker (create workspace, accept link, sign in, refresh, replay): run once the stack is up

## Slice 2: Backend the UI depends on
- [x] `GET /v1/chunks/{chunk_id}`: passage text and metadata, tenant-scoped including global rows
- [x] Handoff: while a conversation is escalated, customer messages go to the agent and the assistant is silent; resolving hands back
- [x] Persist the turn when the client disconnects (Stop button): shield persistence and ticket creation from cancellation
- [x] `GET /v1/events`: `platform/events` port with Postgres `LISTEN/NOTIFY` and in-memory adapters
  - [x] One listener per API process, reconnect, bounded per-subscriber queues, `resync` on drop, `reauth` at token expiry
  - [x] Filter by tenant, owner and role; per-user connection cap; exempt from `RateLimitMiddleware`
  - [x] Publishers: worker job status, documents, escalations, agent replies, conversation status
- [x] `docs/api/sse-contract.md`, `openapi.json`, ADR, unit, integration (two listeners) and security tests

## Slice 3: Scaffold, design system, sign-in
- [x] `frontend/` with npm, strict TypeScript, ESLint, Vitest, Playwright; types from `docs/api/openapi.json` with a CI drift check (`npm run api:check`)
- [x] Same-origin API (Vite proxy in dev; nginx in compose in Slice 6); proxy target from env only (`API_PROXY_TARGET`)
- [x] Design tokens (zero chroma, light and dark), self-hosted fonts, shadcn-style base components
- [x] Glass as the primary surface style (levels 1 and 2, solid fallbacks, contrast test) over a static monochrome ambient backdrop
- [x] API client: in-memory token, single-flight refresh, role-aware route guards
- [x] Screens: sign-in, accept invite and reset password (token from the URL fragment, scrubbed), top-bar shell, theme toggle, Cmd/Ctrl K
- [x] `useEvents` hook: fetch-based stream, backoff, invalidation by event type, full invalidate on `resync` and after every reconnect, re-auth on `reauth`
- [x] Unit tests (client, guards, fragment token, event stream and hook, contrast) and mocked Playwright specs at phone and desktop width in light and dark
- [x] Design review: screenshots of the Slice 3 screens in both themes at both widths checked against the rules (`E2E_SCREENSHOT_DIR=screenshots npm run e2e`)

## Slice 4: Chat
- [x] Streaming over POST with `eventsource-parser` feeding a pure reducer; tokens batched per animation frame
- [x] Sanitised markdown, citation markers as buttons
- [x] Glass citation panel loading the passage (bottom sheet on phones)
- [x] Inline approval card; composer locked while pending
- [x] Stop, retry, history slide-over, handoff state, live agent replies
- [x] Unit tests (parser, reducer, frame batching, sanitisation, approval and handoff logic) and mocked Playwright specs (answer with citation, approve and deny, handoff with a live agent reply, stop, history switch) at phone and desktop width in light and dark
- [x] Design review of the chat states in both themes at both widths; rounder glass (shared radius token, backdrop contrast, softer shadow), pill composer, right-aligned user block (ADR 0010)

## Slice 5: Inbox, knowledge base, team
- [x] Inbox (agent, admin): split list and thread, reply, resolve (ADR 0011)
- [x] Knowledge base (admin): upload, live job status, failure reason (the document list now returns `error_message`), re-index, delete
- [x] Team (admin): members, roles, deactivate, invites with copy link, reset link
- [x] Navigation by role (table-driven guards; role-gating specs)
- [x] Design review: screenshots of every screen in both themes against the design rules

## Slice 6: Delivery
- [x] `infra/docker/web.Dockerfile`, nginx (SSE buffering off, security headers, CSP), `web` service in compose; API behind the proxy with `--proxy-headers` so the throttle sees client addresses (ADR 0014)
- [x] CI `frontend` job: lint, typecheck, API type drift check, unit, build, mocked Playwright (added in Slice 3)
- [x] `.gitignore`, `.dockerignore`, `.gitattributes`, README section, arc42 update
- [ ] Real-stack smoke run

## Slice 7: Caching (ADR 0015)
- [x] Cache port `platform/cache` (get, set with TTL, delete by prefix, bounded, counters): in-memory LRU+TTL default, optional Redis adapter and compose profile; `CACHE_*` settings synced to `.env.example`
- [x] Key rule: tenant (and role) in every key, keyed hash of normalised text, TTL and bound on every entry, security tests for no cross-tenant and no cross-role hit
- [x] Embeddings: query embeddings cached per tenant; ingestion and re-index skip chunks whose content hash already has a vector
- [x] Retrieval results and safety/router verdicts cached for a short TTL, keyed by tenant, role and a per-tenant corpus version bumped by `document.changed`; fail-closed results never cached
- [x] Answers stay uncached (no semantic caching)
- [x] Provider prompt caching: fixed system prompt first; cached input tokens recorded; Anthropic `cache_control` deliberately not added (prefix far below the minimum, see ADR)
- [x] HTTP caching: `ETag` and `Cache-Control: private, max-age` on `GET /v1/chunks/{id}`, `ETag` and `private, no-cache` on the document list, `304` after authorisation, `no-store` on every auth route and on events (OpenAPI schema unchanged)
- [x] Shared state: login throttle and rate limiter on Redis when it is the backend (fixed windows, in-process fallback if Redis is down)
- [ ] Per-user event-stream cap on Redis (needs leases with heartbeats; stays per process, see ADR 0015)
- [x] Observability: hit/miss/eviction counters on `/metrics`, `cache_hit` on the safety, route and retrieval observations
- [x] Tests: unit, security, graph (before/after model calls), Redis adapter against a fake client (real server opt-in)
- [ ] Frontend: `staleTime` per query class, prefetch a passage on citation hover or focus (suggested in ADR 0015, another agent owns `frontend/src`)

## Known limits carried forward
- The sign-in throttle is per process unless `CACHE_BACKEND=redis` (ADR 0007, ADR 0015); the event-stream cap is always per process.
- Two simultaneous refreshes from one browser can end the session; the client refreshes single-flight.
- An access token outlives a role change or a disable by up to `AUTH_ACCESS_TOKEN_MINUTES`.
- The CI `frontend` job is suspended (skipped unless the repository variable `RUN_FRONTEND_CI` is `true`) while the UI keeps changing; the checks still run locally (`npm run lint`, `typecheck`, `api:check`, `test`, `e2e`).

## Liquid redesign (ADR 0016, branch `feat/frontend-liquid-redesign`)
- [x] Inbox "Reconnecting" plus "could not be loaded": first successful stream connection after failures refetches; list retries while in error; no "0" counts beside an error (unit test)
- [x] Tokens: monochrome oklch, three glass thicknesses with solid fallbacks, contrast test per tier, Geist and Instrument Serif self-hosted with measured fallbacks
- [x] Liquid WebGL background (half resolution, 30 fps cap, paused when hidden, still frame under reduced motion, CSS fallback)
- [x] Rim light that follows the pointer, custom cursor, shared springs, three button levels
- [x] Shell: floating glass sidebar, capsule header, phone tab bar and Account sheet, the document never scrolls (Playwright check on every route)
- [x] Chat: no boxes, serif greeting with a gliding composer, trace rows, approval row, source chips, citation panel
- [x] Inbox, Knowledge, Team: thick table surfaces, sticky glass headers, hairline rows, row menus, inline role select, mono status labels, drop strip, one primary button per view
- [x] Sign-in, accept-invite and reset-password on the new panel
- [x] Skeletons, empty states and error states on every list
- [x] Helper text rewritten, one short line each
- [x] Nested `<main>` on the not-allowed page fixed (test)
- [x] Lint, typecheck, API drift, Vitest and the mocked Playwright suite (phone and desktop, light and dark) pass
- [ ] Refraction on small glass elements: dropped on purpose (Chromium garbles `backdrop-filter: url() blur()`); revisit if browsers fix it
- [ ] Soft fade at scroll edges: dropped on purpose (a mask on a scroller flattens its glass children)
- [ ] Per-token streaming fade: approximated by a fade on the last block per batch
- [ ] Virtualise history, inbox and document lists: not done, the API pages them; revisit past the caps
- [ ] Performance numbers for Inbox, Knowledge and Team at 100 rows, and on a real mid-range laptop
- [ ] Apply a logo (three concepts in `docs/frontend/logo-concepts/`, none chosen); favicon, apple touch icon and Open Graph image follow the choice

