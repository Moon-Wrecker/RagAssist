# ADR 0014: Web Delivery: Built SPA on Unprivileged nginx, Same Origin as the API

## Context & Problem
The web app (ADR 0009) needs to ship with the stack. The refresh cookie is `SameSite=Strict` (ADR 0007), so the app
and the API must share one origin. The API has two long-lived streams (ADR 0008) that a default proxy would buffer,
a 50 MiB upload route, and a per-address sign-in throttle that is useless if every request appears to come from the
proxy. AGENTS.md forbids any host, port, role name or credential in code, Docker files or CI.

## Decision
1. **One image, two stages** (`infra/docker/web.Dockerfile`). A Node 22 stage runs `npm ci` and `npm run build`
   (`tsc --noEmit && vite build`, the type-check and build the CI `frontend` job also runs, so a type error fails the
   image build). The runtime stage copies only `dist/` and the nginx templates. The build context is the repository
   root, trimmed by `infra/docker/web.Dockerfile.dockerignore` (an allow-list: `frontend/` and `infra/nginx/`, minus
   `node_modules`, `dist`, `screenshots`, `test-results`, `playwright-report`).
2. **`nginx/nginx-unprivileged`, not `nginx`.** Both are NGINX Inc. images. The unprivileged one runs as uid 101,
   keeps its pid and temp files in `/tmp`, and listens on a port above 1024, so the container needs no root and no
   extra capability. It keeps the official image's template mechanism: verified by running it, `15-` and `20-`
   entrypoint scripts run and `/etc/nginx/templates/*.template` is rendered into a `/etc/nginx/conf.d` that the
   non-root user can write. One thing to watch: Docker Hub moved it (releases from stable 1.30.6 are under
   `nginx/nginx-unprivileged`; `nginxinc/nginx-unprivileged` is archived), so the repository name must be followed.
3. **Pinned tag.** `nginx/nginx-unprivileged:1.30.6-alpine` (the stable track at the time of writing; the mainline is
   1.31.x) and `node:22-alpine`. Tags are rebuilt weekly for base-image fixes, so for a bit-for-bit reproducible build
   pin the digest too: `docker buildx imagetools inspect nginx/nginx-unprivileged:1.30.6-alpine`, then
   `--build-arg NGINX_IMAGE=nginx/nginx-unprivileged:1.30.6-alpine@sha256:<digest>`. We pin the tag, not the digest,
   so security rebuilds arrive with each image build.
4. **Everything deployment-specific comes from `.env`.** Templates: `default.conf.template` (server),
   `proxy.inc.template` (shared proxy settings) and `security-headers.inc.template` (the headers). The only
   substituted variables are `WEB_PORT`, `WEB_SERVER_NAME`, `WEB_API_UPSTREAM` (`host:port`) and `WEB_HSTS`. The
   `.inc` files are included explicitly because nginx drops server-level `add_header` in any location that declares
   its own. An entrypoint include (`15-web-env.envsh`, sourced by the image before rendering) stops the container with
   the variable's name when a required one is missing, is not a number above 1023, or the upstream carries a scheme
   or path. These keys are documented in `.env.example` and are not `Settings` fields (the API never reads them);
   `tests/hygiene/test_env_example.py` lists them explicitly and checks compose reads each.
5. **Proxy rules.** `/v1/` and `/healthz` go to the API over HTTP/1.1 with the `Connection` header cleared.
   `GET /v1/events` and `POST /v1/conversations/{id}/messages` (the two `text/event-stream` responses) have
   `proxy_buffering off`, `proxy_cache off`, `gzip off`, `X-Accel-Buffering: no` and a one-hour read timeout.
   `POST /v1/documents` takes up to 52 MiB (the API enforces 50 MiB; the rest is multipart framing); every other
   location takes 1 MiB. `gzip` covers text assets only (never `text/event-stream`, and not API JSON, which carries
   tokens and would invite BREACH-style attacks). `/docs`, `/openapi.json` and `/metrics` are not proxied.
6. **Client address.** nginx is the edge: it sets `X-Forwarded-For` to `$remote_addr`, overwriting what a client sent
   (uvicorn takes the first entry when it trusts `*`, so appending would let a client pick its own throttle key),
   plus `X-Forwarded-Proto` and `X-Forwarded-Host`. The API runs uvicorn with proxy headers on and
   `forwarded_allow_ips` from the new setting `TRUSTED_PROXY_IPS` (empty = uvicorn's loopback-only default;
   `.env.example` ships loopback plus the private ranges a compose network uses, so a public client cannot spoof the
   header). `ragassist serve` passes both to `uvicorn.run`.
   *Limit:* a TLS-terminating load balancer in front of nginx must be added with `set_real_ip_from`, and
   `X-Forwarded-Proto` is then the balancer's `$scheme` to carry through; this is not built yet.
7. **Security headers.** CSP: `default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'
   data:; font-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'self';
   frame-ancestors 'none'; object-src 'none'`. Also `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
   a `Permissions-Policy` that disables camera, microphone, geolocation and similar, `Cross-Origin-Opener-Policy` and
   `Cross-Origin-Resource-Policy: same-origin`. `Strict-Transport-Security` is sent only when `WEB_HSTS` is
   non-empty (nginx omits a header whose value is empty; verified), because HSTS over plain HTTP is ignored at best and
   pins a development host at worst.
8. **Caching.** `/assets/*` (content-hashed by Vite): `public, max-age=31536000, immutable`, on successful responses
   only, so a 404 is never cached; a missing asset is a 404, not the app shell. `index.html`, `theme-init.js` and every
   client route: `no-cache`. API: `no-store`. Dotfiles: 404.
9. **Compose.** A `web` service (build from the root context, `restart: unless-stopped`, healthcheck against its own
   `/web-healthz`, published on loopback only, environment entirely `${WEB_*}` from `.env`). `depends_on: api:
   service_healthy` with `restart: true`, because nginx resolves the API's address at start and would otherwise keep a
   stale address when the API container is recreated. The `api` service gained a healthcheck (it had none) so the
   dependency can wait for it. Nothing else in the stack changed.

## Consequences
- **Positive:** one origin, so the cookie stays `SameSite=Strict` with no CORS credentials; non-root container; no
  value baked into the image; streams arrive frame by frame; the real client address reaches the throttle.
- **Negative:** `style-src` needs `'unsafe-inline'`. Measured against the built app (see below), Radix injects one
  `<style>` element when a dialog or palette opens (scroll lock). Scripts stay strict, so an injected style cannot run
  code. A narrower option works today: `style-src 'self' 'sha256-<hash of that element>'` produced no violation across
  all specs, but the hash changes with a Radix release, so it was not chosen.
- **Negative:** nginx resolves the upstream once at start (hence `restart: true`); a TLS terminator in front of nginx
  needs real-IP configuration; the base image tag moves weekly unless the digest is pinned.
- **Operational:** set `WEB_BASE_URL` to the origin the browser uses (the cookie endpoints compare `Origin` with it).
  Behind TLS set `AUTH_COOKIE_SECURE=true`, `WEB_HSTS` and an `https` `WEB_BASE_URL`.

## Verification (2026-11-10)
- Built the image with Docker 29; the type-check and `vite build` ran inside it.
- Rendered the templates in a throwaway container and ran `nginx -t`; a missing variable, a port below 1024 and an
  upstream with a scheme each stopped the container with the right message; the process runs as uid 101.
- **CSP:** served the built app from that container and ran the whole mocked Playwright suite (112 specs, desktop
  light and phone dark: sign-in, chat with streaming, inbox, knowledge, team, role gating) with a
  `securitypolicyviolation` listener and console capture in every page: zero violations. The same run with
  `style-src 'self'` produced violations on every dialog and palette open (proving the listener works and that
  `'unsafe-inline'` is needed); with a single hash instead it produced none.
- A stand-in upstream streaming one frame per second showed the frames arriving one per second through
  `/v1/events`; a client-sent `X-Forwarded-For` reached the upstream replaced by the real peer address; `WEB_HSTS` set
  and empty behaved as designed; a 51 MB body was accepted on `/v1/documents` and a 2 MB body refused elsewhere.
- Not verified: a real stack run (API, database, real SSE from the app) and TLS; those are the user's smoke run.

## Consulted
- Docker Hub, official `nginx` image page (2026-11-10): stable track 1.30.6, mainline 1.31.8; "Using environment
  variables in nginx configuration" (`/etc/nginx/templates/*.template` rendered with `envsubst` into
  `/etc/nginx/conf.d`, `NGINX_ENVSUBST_*`, output directory must be writable by the running user); the non-root
  section pointing to the unprivileged image. https://hub.docker.com/_/nginx
- Docker Hub `nginx/nginx-unprivileged` and the `nginx/docker-nginx-unprivileged` repository README: port 8080, no
  `user` directive, pid and temp paths under `/tmp`, tags rebuilt weekly, pin a digest for a fixed image; releases
  from 1.30.6 are published under `nginx/nginx-unprivileged` (`nginxinc/nginx-unprivileged` is archived).
  https://hub.docker.com/r/nginx/nginx-unprivileged , https://github.com/nginx/docker-nginx-unprivileged
- nginx documentation on `add_header` inheritance and `always`, `proxy_buffering`, `X-Accel-Buffering`, `gzip_types`,
  `try_files` and `client_max_body_size` (nginx.org), checked by running the configuration rather than only reading it.
- uvicorn 0.54 `ProxyHeadersMiddleware` source (installed): `forwarded_allow_ips` accepts addresses and CIDR networks,
  defaults to loopback, and takes the first `X-Forwarded-For` entry when `*` is trusted, which decided the overwrite
  rule in item 6. https://www.uvicorn.org/deployment/
- MDN Content-Security-Policy and Strict-Transport-Security; OWASP Secure Headers Project (header set and values).
- Compose `depends_on` long syntax with `condition` and `restart` (Docker Compose specification).
