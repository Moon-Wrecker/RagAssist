# Develop the frontend

**Type:** How-to · **Audience:** a frontend developer · **Verified against:** `a989287`

**In plain English:** The web app is in the folder `frontend/`. It is a React single-page app that Vite builds. This page
shows how to run it with live reload against a running API, how to run its checks and tests, and how to take
screenshots. You need a running backend first.

## Goal

Run the web app in development mode and run the same checks that CI runs.

## Before you start

- Node 22 or newer (`engines.node` in `frontend/package.json` is `>=22`).
- A running API. Start the stack as in [run the stack locally](../tutorials/01-run-the-stack-locally.md). The `api` port is
  published on loopback only.
- You know the folder layout. Read the [frontend structure reference](../reference/frontend-structure.md). The source folders
  are `src/api`, `src/app`, `src/auth`, `src/background`, `src/components`, `src/events`, `src/features`, `src/lib`,
  `src/pages`, `src/test` and `src/theme`. Each feature folder (`auth`, `chat`, `inbox`, `knowledge`, `team`) holds one screen area.

## Steps

1. Open a terminal in the folder `frontend/`.
2. Install the packages:

   ```bash
   npm ci
   ```

3. Copy the template to a local file: copy `frontend/.env.example` to `frontend/.env`. Git ignores `frontend/.env`.
4. Set `API_PROXY_TARGET` in `frontend/.env` to the origin of the running API, for example
   `http://localhost:<API_PORT>`. Replace `<API_PORT>` with the port that compose publishes for the API.

   `npm run dev` stops with the error "API_PROXY_TARGET is not set" when the value is missing. The browser talks only to the
   Vite origin. Vite forwards `/v1` and `/healthz` to the API, so the refresh cookie stays same-origin.

5. Tell the backend to trust the Vite origin. In the **backend** `.env`, the Vite origin must be in `WEB_BASE_URL` or in
   `CORS_ORIGINS`. The template `WEB_BASE_URL` already names the Vite origin, and the template `CORS_ORIGINS` lists it. If you
   changed them for the web container, add the Vite origin to `CORS_ORIGINS` and recreate the API:
   `docker compose up -d --force-recreate api`.
6. Start the dev server:

   ```bash
   npm run dev
   ```

7. Open the address that Vite prints. Sign in as in [create a workspace and sign in](../tutorials/02-create-a-workspace-and-sign-in.md).
8. Edit a file under `src/`. The page reloads.

## The scripts

| Script | What it does |
|---|---|
| `npm run dev` | Starts the Vite dev server. Needs `API_PROXY_TARGET`. |
| `npm run build` | Runs `tsc --noEmit && vite build` |
| `npm run preview` | Serves the build |
| `npm run lint` | Runs ESLint |
| `npm run typecheck` | Runs `tsc --noEmit` |
| `npm test` | Runs the unit tests once (Vitest) |
| `npm run test:watch` | Runs Vitest in watch mode |
| `npm run e2e` | Builds the app and runs the Playwright specs with mocked API calls |
| `npm run api:types` | Regenerates `src/api/schema.d.ts` from `docs/api/openapi.json` |
| `npm run api:check` | Fails when the committed types differ from the generated ones |

## Run the browser tests

1. Install the browser once:

   ```bash
   npx playwright install chromium
   ```

2. Run the specs:

   ```bash
   npm run e2e
   ```

   The specs need no backend. They use mocked responses. To fix the port, set the environment variable `PLAYWRIGHT_WEB_PORT` in your shell
   before you run the command. An empty value picks a free port. Unverified: `playwright.config.ts` reads only the process
   environment, so a value in `frontend/.env` may have no effect.

3. To save screenshots, set the directory:

   ```bash
   E2E_SCREENSHOT_DIR=screenshots npm run e2e
   ```

   On Windows PowerShell set `$env:E2E_SCREENSHOT_DIR = "screenshots"` first.

## Check

Run the same list as the CI job `frontend`, in this order:

1. `npm run lint`
2. `npm run typecheck`
3. `npm run api:check`
4. `npm test`
5. `npm run e2e`

All five commands exit with 0.

> **NOTE.** The CI job `frontend` runs only when the repository variable `RUN_FRONTEND_CI` is `true`. It is off while the
> design changes. Run the five commands yourself before you open a pull request. The CI job `web-image` always builds the
> web image.

## Troubleshooting

- "API_PROXY_TARGET is not set". Fill the value in `frontend/.env`.
- A reload signs you out in dev, or the refresh request answers "Cross-origin request refused." The Vite origin is not in the backend `WEB_BASE_URL` or
  `CORS_ORIGINS`. See step 5.
- The live event stream does not connect. Check the browser network tab for `/v1/events`, and check that the API runs.
- `api:check` fails. The API changed and the types did not. See
  [regenerate API types and OpenAPI](regenerate-api-types-and-openapi.md).
- Playwright cannot find a browser. Run `npx playwright install chromium`.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Frontend structure](../reference/frontend-structure.md)
- [ADR 0009: web app](../adr/0009-web-app.md), [ADR 0010: chat UI](../adr/0010-chat-ui.md) and
  [ADR 0016: liquid redesign](../adr/0016-liquid-redesign.md)
- [Deploy the web container](deploy-the-web-container.md)
