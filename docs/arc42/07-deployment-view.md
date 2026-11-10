# arc42 section 7: Deployment view

Status: covers the web delivery added in ADR 0014. The other arc42 sections are not written yet; this file is the
first, so it stays small and links to the ADRs that hold the reasoning.

## Docker Compose stack (development and single-host)

```
 browser ──HTTP──> web (nginx, non-root, WEB_PORT, published on loopback)
                     │  /            built SPA (frontend/dist), SPA fallback to index.html
                     │  /assets/*    immutable, content-hashed
                     │  /v1/*, /healthz   proxied, same origin (SSE unbuffered)
                     ▼
                   api (uvicorn, behind --proxy-headers, trusts TRUSTED_PROXY_IPS)
                     │
        ┌────────────┼──────────────┬───────────────┐
        ▼            ▼              ▼               ▼
    postgres     localstack      mock-saas       worker (SQS ingestion)
   (pgvector,    (S3, SQS,
     RLS)        Secrets Manager)
```

| Container | Image | Role | Depends on |
|---|---|---|---|
| `web` | built from `infra/docker/web.Dockerfile` on `nginx/nginx-unprivileged` | Serves the SPA, proxies the API, sets security headers | `api` healthy (restarted when `api` is recreated) |
| `api` | built from `infra/docker/api.Dockerfile` | FastAPI HTTP and SSE | `migrate`, `localstack`, `mock-saas` |
| `worker` | same as `api` | Ingestion worker | `migrate`, `localstack` |
| `migrate` | same as `api` | Alembic upgrade, then exits | `postgres` |
| `postgres`, `localstack`, `mock-saas` | Docker Hub images / local build | Data and stand-ins for AWS and the SaaS | none |

## Why one origin

The refresh cookie is `SameSite=Strict` and path-scoped (ADR 0007). Serving the app and the API from the same origin
means the browser always sends it, the API needs no credentialed CORS, and `WEB_BASE_URL` (the origin the cookie-bearing
endpoints accept, and the base of invite links) is simply the address of the `web` container. In frontend development
the Vite dev server plays the same role (`API_PROXY_TARGET`, ADR 0009).

## Configuration

Every host, port and address comes from `.env` (template: `.env.example`). The web container reads `WEB_PORT`,
`WEB_SERVER_NAME`, `WEB_API_UPSTREAM` and `WEB_HSTS`; the API reads `WEB_BASE_URL` and `TRUSTED_PROXY_IPS`. nginx renders
`infra/nginx/templates/*.template` with `envsubst` when the container starts and refuses to start if a required value
is missing.

## Request path properties

- Client address: nginx overwrites `X-Forwarded-For` with the address it saw; uvicorn believes it only from
  `TRUSTED_PROXY_IPS`. The per-address sign-in throttle (ADR 0007) and the API rate limiter therefore count real clients.
- Streams: `/v1/events` and `POST /v1/conversations/{id}/messages` have `proxy_buffering off`, no compression and a
  one-hour read timeout (ADR 0008, `docs/api/sse-contract.md`).
- Uploads: `POST /v1/documents` accepts up to 52 MiB at the proxy; the API enforces its own 50 MiB cap.
- TLS is not terminated here. Behind a TLS terminator set `AUTH_COOKIE_SECURE=true`, `WEB_HSTS` and an `https`
  `WEB_BASE_URL`.
