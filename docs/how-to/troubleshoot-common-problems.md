# Troubleshoot common problems

**Type:** How-to · **Audience:** a developer or operator who sees an error · **Verified against:** `a989287`

**In plain English:** This page lists eight problems that happened in this project. Each row gives the symptom that you see,
the cause and the fix. Find your symptom in the first table. Then open the section below it for the steps.

## Goal

Find the cause of a common problem and fix it in a few steps.

## Before you start

- You can read the logs: `docker compose logs api`, `docker compose logs worker` and `docker compose logs web`.
- You can edit `.env`. Never paste its values into a chat, a ticket or a document.
- You know the compose rule: a container reads `.env` only when compose creates it. After a change to `.env`, run
  `docker compose up -d --force-recreate <service>`. Unverified: the author did not test whether a plain
  `docker compose up -d` recreates a container after an `.env` change, so use the forced form.

## Quick table

| # | Symptom | Likely cause | Section |
|---|---|---|---|
| 1 | Every question gets "I could not run the safety check just now" | `DECIDER_TIMEOUT_MS` is too low, or every decider fails | [1](#1-every-question-is-refused) |
| 2 | The inbox shows "Reconnecting" | The event stream dropped while the API restarted | [2](#2-the-inbox-shows-reconnecting) |
| 3 | The API stops at start with a missing setting | A new required field is not in your `.env` | [3](#3-a-required-setting-is-missing) |
| 4 | A model call returns 404 | The model id is retired or wrong | [4](#4-a-model-returns-404) |
| 5 | Gemini returns 429 or 503 | Quota or load at the provider | [5](#5-gemini-returns-429-or-503) |
| 6 | Sign-in works but the session does not refresh, or you see "Cross-origin request refused." | The browser origin differs from `WEB_BASE_URL` | [6](#6-the-refresh-cookie-is-not-sent) |
| 7 | `docker compose` fails and mentions `WEB_*` | A required web value is empty in `.env` | [7](#7-compose-fails-for-missing-web-values) |
| 8 | Your code change has no effect | The container uses the old image | [8](#8-the-container-has-old-code) |

## 1. Every question is refused

**Symptom.** The chat answers every question with: "I could not run the safety check just now, so I cannot answer yet.
Please try again in a moment." The category in the log is `safety_check_error`.

**Cause.** The safety check [fails closed](../glossary.md). When every member of the decider chain fails or times out,
the system refuses to answer. The setting `DECIDER_TIMEOUT_MS` is 8000 in `.env.example`. A much lower value makes every
member time out. Removing `rules` from `DECIDER_CHAIN` has the same result in a total model outage.

**Fix.**

1. Open `.env`.
2. Check that `DECIDER_TIMEOUT_MS` is not too low. Use the template value.
3. Check that `DECIDER_CHAIN` ends with `rules`.
4. Check the provider keys. See [configure LLM providers and fallbacks](configure-llm-providers-and-fallbacks.md).
5. Run `docker compose up -d --force-recreate api`.

> **CAUTION.** Do not lower the safety check to make the error go away. The refusal is the safe behavior.

## 2. The inbox shows "Reconnecting"

**Symptom.** The status indicator in the inbox shows "Reconnecting" instead of "Live".

**Cause.** The live event stream was down while the API restarted. The record of this incident is in
[ADR 0016](../adr/0016-liquid-redesign.md). The code now keeps a flag for the missed start. The event stream reconnects with a growing
delay, and the inbox list retries every 8 seconds while it shows an error. Unverified: the nginx proxy looks up the address of `api` only once, at start. A stale address after an API
recreate is a possible cause that the author did not reproduce.

**Fix.**

1. Wait 10 seconds. The page retries by itself.
2. If it stays, check that the API is healthy: `docker compose ps`.
3. Recreate the web container so that nginx looks up the address again: `docker compose up -d --force-recreate web`.
4. Reload the page.

## 3. A required setting is missing

**Symptom.** The API, the worker or a command stops at start. The error names a setting.

**Cause.** The code added a required field to `src/ragassist/shared/config/settings.py`. A field without a default is
required. Your `.env` is older than the code.

**Fix.**

1. Compare your `.env` with `.env.example`. The test `tests/hygiene/test_env_example.py` keeps the template in step with
   the settings.
2. Add the missing name with a value for your machine. Take a safe value from the template. Generate your own secrets.
3. Recreate the containers: `docker compose up -d --force-recreate api worker`.

> **WARNING.** Do not run `ragassist init-env --force` to fix this. It replaces the whole `.env` with no backup and makes new
> database passwords that an old database volume rejects.

## 4. A model returns 404

**Symptom.** A call fails with 404 and the log names a model id.

**Cause.** The provider retired the id. The names `claude-3-5-sonnet-20241022` and `claude-3-5-haiku-20241022` stay in
`config/models.yaml` only so that old configs still resolve. They return 404.

**Fix.**

1. Find the setting that names the model: one of the `LLM_ROLE_*` settings or `config/models.yaml`.
2. Choose a current model or alias. See the [models catalog](../reference/models-catalog.md).
3. Recreate the containers. If you edited `config/models.yaml`, rebuild them (see section 8).

## 5. Gemini returns 429 or 503

**Symptom.** Answers are slow or use another model. The log shows errors from the `gemini` provider with the status 429
(rate limit or quota) or 503 (overloaded).

**Cause.** The provider limits requests or is busy. This is a normal event. The fallback chain exists for it. The generate
step tries each model in order. The decision layer moves to the next `llm_structured` member, and the retry count for a
decider model is 1 (`DECIDER_MODEL_MAX_RETRIES`).

**Fix.**

1. Check that a fallback of another provider is set, for example `LLM_ROLE_GENERATOR_FALLBACKS=claude-haiku`. See
   [configure LLM providers and fallbacks](configure-llm-providers-and-fallbacks.md).
2. Check that the key of that provider is set. A provider with no key is dropped from the fallbacks.
3. If every model fails, the generate step re-raises the last error. Wait and retry, or raise your quota at the provider.

## 6. The refresh cookie is not sent

**Symptom.** You sign in, but a reload signs you out. Or the refresh request answers 403 with "Cross-origin request refused."

**Cause.** The cookie `ragassist_refresh` is `HttpOnly` with `SameSite=Strict` and the path `/v1/auth`. The endpoints that use
it compare the `Origin` header of the request with `WEB_BASE_URL` (and `CORS_ORIGINS`). The scheme, host and port must match
exactly. A second cause: `AUTH_COOKIE_SECURE=true` on plain HTTP. The browser then refuses to keep the cookie.

**Fix.**

1. Look at the address bar. Note the scheme, host and port.
2. Set `WEB_BASE_URL` in `.env` to exactly that origin, for example `http://localhost:<WEB_PORT>`.
3. For plain HTTP on your machine, set `AUTH_COOKIE_SECURE=false`. Use `true` only over HTTPS. Staging and production need
   `true`.
4. Recreate the API: `docker compose up -d --force-recreate api`.
5. Sign in again.

See also [deploy the web container](deploy-the-web-container.md).

## 7. Compose fails for missing WEB values

**Symptom.** `docker compose up` or `docker compose config` stops with a message such as `run ragassist init-env` or
`set it in .env (see .env.example)`. Or the `web` container starts and stops, and its log begins `15-web-env:`.

**Cause.** The `web` service needs `WEB_PORT`, `WEB_SERVER_NAME` and `WEB_API_UPSTREAM`. An empty value stops compose. The entry script
of the container also stops for a `WEB_PORT` that is not a number or is below 1024, and for an upstream that has a
scheme (`://`), a path or a space. `WEB_HSTS` is optional.

**Fix.**

1. Open `.env`.
2. Set `WEB_PORT` (1024 or higher), `WEB_SERVER_NAME` (`_` is allowed) and `WEB_API_UPSTREAM` as `host:port`. Take the
   template values from `.env.example`.
3. Run `docker compose up -d --build web`.

## 8. The container has old code

**Symptom.** You changed Python code, `config/models.yaml`, a migration or the frontend. The running system behaves as before.

**Cause.** The images copy `src/`, `config/`, `alembic.ini`, `migrations/` and `seed/` at build time. There is no bind mount.
The frontend is built into the `web` image.

**Fix.**

1. For Python code or `config/`: `docker compose up -d --build api worker`.
2. For a new migration: rebuild so that `migrate` has the file: `docker compose up -d --build migrate api worker`.
3. For the frontend: `docker compose up -d --build web`.

A clean build can fail at the step `COPY seed/ seed/` in `infra/docker/api.Dockerfile`, because the folder
`seed/` is not in git at this commit.

## Check

- After the fix, `docker compose ps` shows no `unhealthy` or `restarting` service.
- A question in the chat gets an answer.
- A sign-in survives a page reload.

## Troubleshooting links

- [Command-line reference](../reference/cli.md)
- [Configuration reference](../reference/configuration.md)
- [Error responses](../reference/error-responses.md)
- [Observability](../reference/observability.md) and [configure tracing](configure-tracing.md)
- [Risks and technical debt](../arc42/11-risks-and-technical-debt.md)
