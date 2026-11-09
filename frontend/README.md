# RagAssist web app

React 19 single-page app for customers, support agents and admins. Vite, strict TypeScript, React Router, TanStack
Query, Tailwind 4, shadcn-style components, Motion, Vitest and Playwright. Design and architecture decisions are in
`docs/adr/0009-web-app.md`; the to-do list is `docs/frontend/TODO.md`.

## Run it

```bash
cd frontend
npm ci
cp .env.example .env     # then set API_PROXY_TARGET to the origin of a running RagAssist API
npm run dev
```

The browser only ever talks to the Vite origin. `/v1` and `/healthz` are proxied to `API_PROXY_TARGET`, so the refresh
cookie is same-origin and stays `SameSite=Strict`. The API must trust the dev origin for its CSRF check: put it in
`WEB_BASE_URL` (or `CORS_ORIGINS`) in the backend `.env`. Nothing in the code, config or tests names a host or port;
the dev server prints its own address and Playwright asks the OS for a free port.

| Script | What it does |
|---|---|
| `npm run dev` / `build` / `preview` | Vite dev server (needs `API_PROXY_TARGET`), type-check plus production build, preview of the build |
| `npm run lint` / `typecheck` | ESLint, `tsc --noEmit` |
| `npm test` | Vitest unit tests |
| `npm run api:types` | Regenerate `src/api/schema.d.ts` from `../docs/api/openapi.json` |
| `npm run api:check` | Fails if the committed schema differs from a fresh generation (CI drift check) |
| `npm run e2e` | Mocked Playwright specs (phone and desktop, light and dark). Needs `npx playwright install chromium` once |
| `E2E_SCREENSHOT_DIR=screenshots npm run e2e` | Also writes a screenshot of every screen into `frontend/screenshots/` (git-ignored) |

## Layout

```
src/api          fetch client (in-memory token, single-flight refresh), auth calls, generated types, query keys
src/auth         auth context and provider, route guards, URL-fragment token handling
src/app          route table (one source for navigation and guards), routes, providers
src/events       live-event stream (fetch + eventsource-parser), invalidation map, useEvents hook
src/components   shell (top bar, palette), panel, status page; ui/ holds the shadcn-style primitives
src/features     feature screens (auth; chat: stream parser, pure turn reducer, frame batcher, markdown, citations, approval)
src/theme        theme context and provider, contrast test for the design tokens
tests/e2e        mocked Playwright specs; every /v1 call is intercepted, no backend runs
```

## Sessions

- The access token lives in module memory only. A reload starts signed out and restores the session through
  `POST /v1/auth/refresh` and the httpOnly cookie.
- A 401 triggers one refresh and one retry. Concurrent 401s share one refresh (single flight, plus a Web Lock across
  tabs), because the server rotates the cookie and treats a replayed token as theft (ADR 0007). If the refresh is
  refused the session ends and the app shows sign-in; if the server cannot be reached the session is kept.
- Invite and reset links carry their secret in the URL fragment (`/accept#token=...`). The page reads it once,
  removes it from the address bar and history entry, and holds it in memory until the password is accepted.
- Role access comes from one table (`src/app/access.ts`): customers get Chat, agents add Inbox, admins add Knowledge
  and Team. Guards and navigation both read it. The server still enforces every rule.
- `useEvents` keeps the query cache fresh from `GET /v1/events` (`docs/api/sse-contract.md`): exponential backoff
  with jitter, `Retry-After` on the stream cap, an idle watchdog, invalidate-everything on `resync` and after every
  reconnect, refresh and reconnect on `reauth`.

## Design rules

- **True monochrome.** Every colour token has zero chroma, in light and dark (a test enforces it). Status is carried
  by glyph, weight and pattern, never colour. Light and dark follow the system, with a toggle (System, Light, Dark).
- **Glass is the primary surface style.** The top bar, the sign-in, invite and reset panels, dialogs, the palette,
  menus, and later the composer, side panels and table or list containers are translucent neutral surfaces:
  `glass-1` for panels on the page, `glass-2` for floating layers. Each has a translucent neutral fill, a modest
  `backdrop-filter: blur() saturate()`, a hairline border with a faint light top edge and a very soft shadow. Never
  put glass inside glass; small controls (inputs, buttons, menu rows) are not glass.
- **A monochrome backdrop for the glass to blur.** `.ambient` is a fixed, static layer of four large soft grey
  shapes (light: white and grey; dark: grey and black) plus faint grain. CSS only, no images, no gradients, nothing
  animates, so scrolling stays cheap (blur radii are modest and smaller on phones).
- **Safeguards.** Solid fallbacks apply under `@supports not (backdrop-filter)` and `prefers-reduced-transparency`
  (the backdrop is hidden too). `src/theme/contrast.test.ts` computes text contrast for body and muted text on both
  glass levels over the lightest and darkest backdrop tone, in both themes, and on the solid fallbacks: WCAG AA.
- **Type.** Instrument Serif for page and thread titles only, Geist Sans for the interface, Geist Mono for metadata,
  citations and status. All self-hosted from npm (`@fontsource/*`), Latin subset.
- **Shape and motion.** Hairline borders, generous radii on glass (`rounded-3xl` panels and dialogs, pill composer, chips and tags), a soft diffuse shadow. Motion (the
  library) only, short and functional; `MotionConfig reducedMotion="user"` honours `prefers-reduced-motion`.
- **Banned:** gradients, sparkle icons, emoji, purple or any hue, glowing edges, cards inside cards, centred hero
  prompts, chat bubbles for both sides, "How can I help you today?", fake suggestion chips.
- **Plain empty states** that say what to do next. Everything is keyboard reachable with visible focus, a skip link,
  and `aria-live` regions for status and errors. Layouts work down to phone width.

## Notes

- Dependencies are pinned to exact versions at least two weeks old. TypeScript is held at 6.0.x because
  `typescript-eslint` does not yet support 7.
- `npm audit` reports a moderate `minimatch` advisory reachable only through ESLint (dev tooling, not shipped).
- `frontend/src/lib/` is un-ignored in `.gitignore` explicitly because the Python `lib/` rule would hide it.
