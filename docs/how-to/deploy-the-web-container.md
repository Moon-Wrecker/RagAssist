# Deploy the web container

**Type:** How-to · **Audience:** an operator who serves the web app · **Verified against:** `a989287`

**In plain English:** The `web` container holds the built web app and an nginx server. The server also forwards API calls
to the `api` container, so the browser sees one address. This page shows how to set the values that the container needs,
start it, check it and put TLS in front of it. It also lists the limits of the proxy.

## Goal

Serve the web app and the API from one origin, with the right settings for cookies and headers.

## Before you start

- You know why one origin matters. The refresh cookie `ragassist_refresh` uses `SameSite=Strict`, so the browser sends it
  only to the same site. Read [ADR 0014: web delivery](../adr/0014-web-delivery.md).
- You have a `.env`. If not, run `ragassist init-env`. See [run the stack locally](../tutorials/01-run-the-stack-locally.md).
- The `api` service works. `web` waits for `api` to be healthy.

## Steps

1. Open `.env`.
2. Set the four values that compose and nginx read. They are not API settings:

   | Name | Meaning | Rule |
   |---|---|---|
   | `WEB_PORT` | The port nginx listens on inside the container and the loopback port that compose publishes | A number of 1024 or higher |
   | `WEB_SERVER_NAME` | The nginx `server_name` | `_` answers for any host name. Use your host name to restrict it. |
   | `WEB_API_UPSTREAM` | The API as `host:port` from inside the compose network | No scheme, no path, no space |
   | `WEB_HSTS` | The value of the `Strict-Transport-Security` header | Empty sends no header. Set it only for HTTPS. |

3. Set `WEB_BASE_URL` to the address that the browser uses. It needs the scheme, the host and the port, for example
   `http://localhost:<WEB_PORT>`. The cookie endpoints compare the `Origin` header with this value exactly.
4. For a deployment on HTTPS, set `AUTH_COOKIE_SECURE=true` and set `WEB_HSTS`, for example `max-age=31536000`.

   > **CAUTION.** With `AUTH_COOKIE_SECURE=true` on plain HTTP, the browser does not keep the cookie and every sign-in
   > seems to fail. Use `true` only when the browser reaches the site over HTTPS. The staging and production
   > environments require it to be `true`.

5. Set `TRUSTED_PROXY_IPS` to the addresses or networks of the proxies that call the API. In the shipped compose file,
   the only such proxy is the `web` container. The template lists the loopback address and the private ranges of a
   compose network. List only your own proxy.
6. Build and start the web container:

   ```bash
   docker compose up -d --build web
   ```

   The image has two stages. A Node 22 stage runs `npm ci` and `npm run build` (which is `tsc --noEmit && vite build`).
   A type error fails the build. The second stage is `nginx/nginx-unprivileged:1.30.6-alpine`.

7. After you change the frontend code, run the same command again. There is no bind mount.
8. After the API container is recreated, nginx restarts by itself. The compose setting `restart: true` on the `api`
   dependency does that, because nginx looks up the address of `api` only once, at start.

## Put TLS in front

1. End TLS in a proxy or load balancer in front of the web container. The container serves plain HTTP.
2. Know the limit. The nginx in the `web` container sets `X-Forwarded-For` to the address that it sees. That address is
   the address of your TLS proxy. The API therefore counts all clients as one address. Support for a real client address
   (`set_real_ip_from`) is not built yet. See [ADR 0014](../adr/0014-web-delivery.md), decision 6.
3. Set `WEB_BASE_URL` to the HTTPS address, `AUTH_COOKIE_SECURE=true` and `WEB_HSTS`.
4. Recreate the containers: `docker compose up -d --force-recreate api web`.

## What the proxy does

- It sends `/v1/` and `/healthz` to the API.
- It does **not** send `/docs`, `/openapi.json` or `/metrics`. Read the API docs on the API address directly.
- It does not buffer the event stream at `/v1/events` or the message route `POST /v1/conversations/{id}/messages`. The
  read timeout is 1 hour.
- It allows 52 MiB on `/v1/documents`. The API limit is 50 MiB. Other routes allow 1 MiB.
- It serves `/assets/*` with an immutable cache header.
- It sends strict security headers, including a content security policy.

## Check

1. Run `docker compose ps`. `web` shows `healthy`.
2. Open `http://localhost:<WEB_PORT>/web-healthz`. The proxy answers with no call to the API.
3. Open `http://localhost:<WEB_PORT>/healthz`. The API answers `{"status":"ok","app":"RagAssist"}`.
4. Sign in. Open the browser tools and look for the cookie `ragassist_refresh` with `HttpOnly`, `SameSite=Strict` and the path
   `/v1/auth`.
5. The CI job `web-image` builds the image and checks the headers. You can run the same checks by reading
   `.github/workflows`.

## Troubleshooting

- The container stops at start. The message begins `15-web-env:`. It names the variable that is empty, a `WEB_PORT` that is not a
  number or is below 1024, or an upstream that has a scheme, a path or a space.
- Compose refuses to start with `run ragassist init-env`. `WEB_PORT` is empty in `.env`.
- The refresh request answers 403 "Cross-origin request refused." (a reload signs you out). `WEB_BASE_URL` does not match the browser address.
- The inbox shows "Reconnecting" after the API restarted. Recreate `web` so that nginx looks up the new address:
  `docker compose up -d --force-recreate web`. Unverified: a stale upstream address is a possible cause that the author did not
  reproduce.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [CI and quality gates](../reference/ci-and-quality-gates.md)
- [Security controls](../reference/security-controls.md)
- [Deployment view](../arc42/07-deployment-view.md)
- [Develop the frontend](develop-the-frontend.md)
