# ADR 0009: Web App: Same-Origin SPA, In-Memory Access Token and a Glass Design System

## Context & Problem
The API has accounts and sessions (ADR 0007) and live events (ADR 0008) but no UI. The web app must keep the
refresh cookie `SameSite=Strict`, never leave a long-lived secret where script can read it, work for three roles on
phones and desktops, and follow a strict visual brief (monochrome, glass, no decoration for its own sake).

## Decision
1. **Vite single-page app in `frontend/`** (React 19, strict TypeScript, React Router, TanStack Query, Tailwind 4,
   shadcn-style components built on Radix and cmdk, Motion for animation). Chosen over a server-rendered framework
   because the app is entirely behind sign-in and talks to an existing API.
2. **Same origin.** The browser only talks to the origin that serves the app. In development Vite proxies `/v1` and
   `/healthz` to `API_PROXY_TARGET` (environment only); in production a reverse proxy does the same (Slice 6). The
   refresh cookie therefore never needs `SameSite=None` or CORS credentials.
3. **Token handling.** The access token is module memory only. After a reload the session is restored with
   `POST /v1/auth/refresh`. A 401 triggers one refresh and one retry; concurrent 401s share one refresh (single
   flight, and a Web Lock across tabs), which removes the "two tabs can end the session" limit listed in ADR 0007 for
   tabs of one browser. A refused refresh ends the session; an unreachable server does not.
4. **Fragment links.** Invite and reset tokens are read from `#token=...`, removed from the URL and history entry,
   and kept in memory until spent.
5. **One access table** (`src/app/access.ts`) feeds both navigation and route guards. Guards are a convenience; the
   server enforces roles.
6. **Live updates** use a fetch-based reader (`EventSource` cannot send `Authorization`) with `eventsource-parser`.
   Events only mark TanStack Query keys stale; there is no client-side copy of server state. Backoff with jitter,
   `Retry-After` on the stream cap, an idle watchdog, invalidate-everything after `resync` and after every reconnect,
   refresh and reconnect on `reauth`.
7. **Types come from the contract.** `src/api/schema.d.ts` is generated from `docs/api/openapi.json` with
   `openapi-typescript`; CI fails if the committed file drifts.
8. **Design system.** True monochrome (zero chroma in every token, enforced by a test), light and dark following the
   system with a toggle, Instrument Serif for titles, Geist Sans and Mono, self-hosted. Glass is the primary surface
   style (translucent neutral fill, modest blur, hairline border with a light top edge, soft shadow) over a static
   monochrome backdrop of blurred flat shapes and grain. It replaces the earlier "glass only on floating layers" rule.
   Safeguards: solid fallbacks without `backdrop-filter` and under `prefers-reduced-transparency`, no glass inside
   glass, modest blur radii, and a contrast test (WCAG AA) over the lightest and darkest backdrop tone. Motion honours
   `prefers-reduced-motion`.

## Consequences
- **Positive:** no secret in script-readable storage; cookies stay `SameSite=Strict`; one place for role rules;
  generated types catch contract drift in CI; the glass look degrades to a plain solid UI.
- **Negative:** a hard reload costs one refresh round trip before the UI renders; `backdrop-filter` has a cost on low
  end phones (mitigated by modest radii, a static backdrop and the reduced-transparency fallback); the dev
  proxy needs the dev origin in the backend's `WEB_BASE_URL` or `CORS_ORIGINS`.
- **Operational:** `frontend/.env.example` documents `API_PROXY_TARGET`. CI has a `frontend` job.

## Consulted
Installed package type declarations and behaviour were checked directly (React Router, Motion, `eventsource-parser`,
Radix, cmdk, `openapi-typescript`, Playwright) together with the running tests. The documentation sites themselves
were not re-fetched while writing this (network access was unreliable), so API usage is verified by types and tests,
not by re-reading the docs. Design and security references: ADR 0007 and 0008; WCAG 2.2 contrast minimums
(1.4.3); MDN on `backdrop-filter`, `prefers-reduced-transparency`, `prefers-reduced-motion`, the Web Locks API and the
URL fragment; the OWASP session management cheat sheet.
