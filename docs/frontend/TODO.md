# Frontend to-do

One checkbox per planned item, updated in the same PR that does the work. Design brief: React with shadcn/ui, black
and white, a little glass, no AI slop. Order: backend first, then UI slices, each its own PR.

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
- [ ] `frontend/` with npm, strict TypeScript, ESLint, Vitest, Playwright; types from `docs/api/openapi.json` with a CI drift check
- [ ] Same-origin API (Vite proxy in dev, nginx in compose); proxy target from env only
- [ ] Design tokens, self-hosted fonts, shadcn base components
- [ ] API client: in-memory token, single-flight refresh, role-aware route guards
- [ ] Screens: sign-in, accept invite and reset password (token from the URL fragment), top-bar shell, theme toggle, Cmd/Ctrl K
- [ ] `useEvents` hook: fetch-based stream, backoff, invalidation by event type, full invalidate on `resync`

## Slice 4: Chat
- [ ] Streaming over POST with `eventsource-parser` feeding a pure reducer; tokens batched per animation frame
- [ ] Sanitised markdown, citation markers as buttons
- [ ] Glass citation panel loading the passage (bottom sheet on phones)
- [ ] Inline approval card; composer locked while pending
- [ ] Stop, retry, history slide-over, handoff state, live agent replies

## Slice 5: Inbox, knowledge base, team
- [ ] Inbox (agent, admin): split list and thread, reply, resolve
- [ ] Knowledge base (admin): upload, live job status, failure reason, re-index, delete
- [ ] Team (admin): members, roles, deactivate, invites with copy link, reset link
- [ ] Navigation by role
- [ ] Design review: screenshots of every screen in both themes against the design rules

## Slice 6: Delivery
- [ ] `infra/docker/web.Dockerfile`, nginx (SSE buffering off, security headers, CSP), `web` service in compose; API behind the proxy with `--proxy-headers` so the throttle sees client addresses
- [ ] CI `frontend` job: lint, typecheck, unit, build, mocked Playwright
- [ ] `.gitignore`, `.dockerignore`, `.gitattributes`, README section, arc42 update
- [ ] Real-stack smoke run

## Known limits carried forward
- The sign-in throttle is per process (ADR 0007).
- Two simultaneous refreshes from one browser can end the session; the client refreshes single-flight.
- An access token outlives a role change or a disable by up to `AUTH_ACCESS_TOKEN_MINUTES`.
