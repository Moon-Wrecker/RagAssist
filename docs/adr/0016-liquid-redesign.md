# 0016: Liquid Redesign of the Web App: Ink in Water Under Three Glass Thicknesses

Status: accepted for Chat and the shell (first part). Inbox, Knowledge, Team and the sign-in pages are only adapted to the new shell and are redesigned next.

## Context

The web app (ADR 0009, 0010, 0011, 0014) is correct but generic: a template shell, boxes inside boxes, one glass recipe. The brief asks for a monochrome "ink in water" background, a macOS-style glass system in three thicknesses, a Chat with no boxes, and a fix for an Inbox that showed "Reconnecting" beside "The conversations could not be loaded." with every tab at 0.

No API contract, auth, routing or stream-reducer behaviour changes. The CI `frontend` job stays suspended on purpose; the checks below are run locally.

## What makes this recognisably RagAssist

1. RagAssist shows its working as quiet trace rows on the page ("Used get_account", "Needs your approval", sources as chips) instead of hiding it behind a spinner, so a customer can see what the assistant looked up and what it may do.
2. Nothing happens to a customer's account without a decision: an action is a hairline-ruled approval row in the conversation itself, with the exact values shown, and the composer locks until they decide.
3. The surface is ink in water: slow monochrome liquid behind the whole app and glass that is thin for controls, regular for navigation and thick for content, so the only thing on the page with weight is the answer.

## Decisions

### Background
- One fixed full-screen WebGL canvas drawn by a fragment shader (domain-warped fbm, the technique in Inigo Quilez's "warping" article), at half resolution, capped at 30 fps, paused when the tab is hidden, one still frame under `prefers-reduced-motion`, with a static CSS version (`.ambient`) when WebGL is missing. No React work per frame: `src/background/liquid.ts` owns its loop.
- A brightness budget (`liquid-config.ts`): floor 0.015, centre 0.27, edge 0.38 in the dark theme, the inverse in light; a soft scrim darkens the reading column. The contrast test reads these numbers, so changing the liquid cannot silently break text contrast.
- Grain at 1.6 percent to avoid banding.

### Glass: three thicknesses (`src/index.css`)
- `glass-thin` (controls, user bubble, chips), `glass-regular` (sidebar, composer, phone tab bar), `glass-thick` (header capsule, dialogs, sheets, palette, citation panel). Blur 10, 24, 40 px with saturation 1.6 and a brightness lift; fill rises with thickness.
- Rim light: thin glass uses inset shadows; regular and thick use a masked gradient `::after` whose bright side follows `--lx/--ly`, which `src/lib/pointer-light.ts` sets from the pointer (one rAF-coalesced write on the root).
- Concentric radii (`--r-outer` minus `--pad`), capsule controls, a sliding glass thumb on the active nav item (motion `layoutId`), press scale 0.97 with a spring `linear()` easing.
- Fallbacks: solid fills when `backdrop-filter` is unsupported or `prefers-reduced-transparency` is set.
- Performance rule: no glass on a repeated item at rest. At most three overlapping blur layers: the sidebar, the header, the composer.
- The header is thick rather than regular: scrolling text under a regular capsule stayed legible through it and collided with the title.

### Dropped on purpose (documented, not hidden)
- Edge refraction (SVG displacement inside `backdrop-filter`): tried and removed. In Chromium `backdrop-filter: url(#filter) blur()` drops or garbles the blur (standalone test and screenshot comparison), which breaks every glass object that carries it. Brief: "never depend on it".
- Soft fade at scroll edges: a CSS mask on a scroller makes it a backdrop root and flattens the glass children, so the "fade" is only the glass blur over the scrolling content.
- Per-token streaming fade: approximated by a CSS fade-in on the last markdown block of each batch, because the reducer and the protocol must not change.
- History virtualisation: the API pages history at 50 rows, so the DOM stays small; rows use `content-visibility: auto`.

### Chat
- No boxes. Assistant text sits on the page; the user's turn is a thin-glass bubble; sources are chips; steps and approvals are hairline-ruled trace rows.
- One composer element glides between "centred under the greeting" and "docked", so there is no jump on the first send.
- The message list is the only scroller (`@shadcn/react` Message Scroller with auto scroll and a jump-to-latest button). The document never scrolls (`overflow: hidden` on html and body); `tests/e2e/layout.spec.ts` checks `scrollHeight === clientHeight` on every route in all four projects.
- Phone: the sidebar becomes a floating tab bar and an Account sheet; history is a sheet.

### Type and tokens
- Geist Sans, Geist Mono (labels, meta) and Geist Serif (page titles, greeting), self-hosted from `@fontsource` (OFL) in `public/fonts`, with fallback faces whose size-adjust, ascent and descent are measured (Arial 104.9 / 87.7 / 21 percent for Sans, Consolas 109.1 / 92.6 / 27.5 for Mono, Georgia 75.8 / 130.6 / 40.9 for Serif) so loading the fonts does not shift the layout. Every colour token has chroma 0; there is no accent.

## Inbox: the "Reconnecting" plus "could not be loaded" screen

Reproduced exactly (indicator "Reconnecting", the error text, tabs "0") by failing `/v1/events` and `/v1/escalations` at page load and then restoring them. Cause: `runEventStream` called `onReconnected` (invalidate every query) only when the stream had been ready before. When the very first successful connection came after failed attempts, the stream said "Live updates on" but the list stayed in its error state for good.

Fix (`frontend/src/events/event-stream.ts`, unit test in `event-stream.test.ts`): a `missedStart` flag so the first successful connection after failures also refetches; the Inbox query retries every 8 s while in error; tab counts are shown only when the list is ready (no "0" beside an error). Verified in a real browser against the real API: it recovers within about 2 s of the API answering.

Facts for the operator, not changed here:
- The trigger is the API being unreachable or restarting while the page is open or loading. The user's API container was recreated at about 02:07 UTC on 2026-11-10 and the old container's logs are gone, so the exact incident cannot be proven from logs. The current API log shows no tracebacks and no 429.
- A silently dead event stream (a proxy that does not propagate the upstream drop) stays "Live updates on" for up to the 45 s idle timeout.
- Latent and unverified: `infra/nginx/templates/proxy.inc.template` uses a static `proxy_pass` with no `resolver`, so nginx resolves `api` once at start. Recreating the API container after the web container started could leave stale-address 502s on every `/v1` call until the web container restarts. Not reproduced (the stack was not restarted on purpose).
- A role `user` opening `/inbox` gets the "not allowed" page, which renders a nested `<main>` (accessibility nit, not fixed here).

## Performance (measured, with caveats)

Headless Chromium 1 worker under Playwright on an AMD Ryzen 7 6800H laptop (16 threads, RTX 3060 Laptop plus integrated Radeon), headless WebGL (probably software rasterised, so the shader numbers are pessimistic for a real GPU and optimistic for a weak CPU). This is not a mid-range laptop and not a phone. Mocked API, a 40-message conversation, a streamed 120-token answer.

| Case | Liquid running | Liquid paused (reduced motion) |
| --- | --- | --- |
| Desktop, idle 5 s | 59.8 fps, p95 16.8 ms | 59.8 fps, p95 16.8 ms |
| Desktop, wheel-scrolling the list | 47.6 fps, p95 33.4 ms | 51.9 fps, p95 33.4 ms |
| Desktop, streaming 120 tokens | 58.6 fps, p99 33.4 ms | 59.4 fps |
| Phone viewport, idle | 60 fps | 60 fps |
| Phone viewport, scrolling | 45.9 fps, p95 33.5 ms | 60 fps |
| Phone viewport, streaming | 54.6 fps with 3 long tasks (max 102 ms) in the first run; 60 fps with none in a repeat | 60 fps |

Reading: the background itself is cheap when nothing else moves; scrolling a list under three blur layers costs frames in this environment (a few fps on desktop, more on the phone viewport) and one streaming run showed three long tasks that did not repeat. Real-device numbers on the target mid-range laptop are still owed.

## Logo concepts (not applied; for the user to choose)

One colour, a 64 unit grid, Geist wordmark; files and a 16 and 48 px preview in `docs/frontend/logo-concepts/`.

1. Merge: two round forms that join at a pinched waist. It says two liquids becoming one (the customer's question and the company's documents) and holds as a bold blob at 16 px, but it is the most generic of the three.
2. Drop on water: a single ink drop over one wave line. It is the most literal reading of "ink in water" and reads at 16 px, at the cost of looking like a utility or weather icon.
3. Flowing R: a heavy rounded R whose leg ends in a falling drop. It is the most ownable and survives 16 px best as a letter, but the liquid idea is only a detail.

## Consulted

- shadcn AI Elements (ui.shadcn.com/docs/ai-elements: message, prompt-input, tool, inline-citation, message-scroller; no package, the code is copied) and `@shadcn/react` 0.3.1 for Chat, Message, Bubble, Input Group, Trace and Message Scroller. Pinned exactly; verified MIT, maintainer shadcn, no dependencies, no install scripts. No Vercel AI SDK: nothing here needs it to render.
- iquilezles.org/articles/warp (domain warping) for the shader.
- Fontsource Geist packages (OFL) for the fonts.
- MDN and the WebKit/Chromium behaviour of `backdrop-filter`, `prefers-reduced-transparency`, `content-visibility`, and the CSS `linear()` easing function.

## Consequences

- One look, three thicknesses, tested for AA contrast on each over the hardest and the easiest backdrop pixel, plus the solid fallbacks.
- Two decorative effects from the brief are not delivered (refraction, scroll-edge fade); both are documented above.
- The `outline` button variant was renamed `secondary` (glass) across the app; buttons have three levels: primary, secondary glass, ghost.
