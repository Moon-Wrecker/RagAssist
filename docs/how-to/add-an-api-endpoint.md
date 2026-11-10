# Add an API endpoint

**Type:** How-to · **Audience:** a backend developer · **Verified against:** `a989287`

**In plain English:** This page shows how to add one HTTP route to the API without breaking the layer rules. The route
stays thin. It checks who the caller is, calls a use case and turns a domain error into an HTTP status. The page ends
with the tests that must pass.

## Goal

Add a new route to an existing module, with the right authentication, schemas, tests and updated API files.

## Before you start

- You know the layers: `domain`, `application`, `adapters` and `api`. The inward rule says that `domain` imports nothing
  from the other layers. Read [why a modular monolith](../explanation/why-a-modular-monolith.md) and the
  [ports and adapters reference](../reference/ports-and-adapters.md).
- You know the terms [Principal](../glossary.md) and [bounded context](../glossary.md).
- You read the example module `src/ragassist/modules/identity/`. Its layout is the template:
  `domain/`, `application/` (with `ports.py`), `adapters/` (`postgres.py` and `memory.py`), `api/` (`router.py`,
  `deps.py`, `schemas.py`) and `wiring.py`.
- Before you code, write down the goal of the route in one or two sentences and record what you consulted. See
  `AGENTS.md`, section 3.5.

> **WARNING.** Take `tenant_id`, `user_id` and `role` only from the verified `Principal`. Never take them from the
> request body, a query string, a model output or a tool argument.

## Steps

1. Write the use case in `application/`. It imports only from `domain/` and from `ports` (Python `Protocol` classes).
2. Add or extend a port in `application/ports.py` if the use case needs new storage.
3. Implement the port twice: in `adapters/postgres.py` and in `adapters/memory.py`. The Postgres code opens a tenant
   scope with `ScopedDatabase.scope(tenant_id)`.
4. Add the request and response models to `api/schemas.py`. They are Pydantic classes.
5. Add the route to `api/router.py`. Take the caller from the dependency:

   ```python
   from fastapi import APIRouter, Depends
   from ragassist.shared.security.deps import get_current_principal, require_role
   from ragassist.shared.security.jwt import Principal, UserRole

   router = APIRouter(prefix="/notes", tags=["Notes"])

   @router.get("", response_model=list[NoteOut], summary="List the notes of the workspace")
   async def list_notes(
       principal: Principal = Depends(get_current_principal),
       services: NotesServices = Depends(get_notes),
   ) -> list[NoteOut]:
       return [NoteOut.of(n) for n in await services.notes.list(principal.tenant_id)]
   ```

   The name `notes` is an invented example. For an admin-only route use
   `principal: Principal = Depends(require_role(UserRole.ADMIN))`, as the team router does.

6. Catch domain errors in the route and convert them. The identity module has `http_error(exc)` in
   `modules/identity/api/deps.py` for this. Use the same style. See [error responses](../reference/error-responses.md).
7. Build the services for the route in `wiring.py` and a dependency such as `get_notes`. The dependency uses the
   Postgres runtime from `active_runtime()` in `src/ragassist/runtime.py` and an in-memory fallback.
8. Mount the router in `create_app()` in `src/ragassist/main.py`:

   ```python
   app.include_router(notes_router, prefix=settings.API_V1_PREFIX)
   ```

9. Add the tag to `TAGS_METADATA` in `src/ragassist/main.py`, with a one-line description.
10. If the route needs a new table, follow [add a database migration with RLS](add-a-database-migration-with-rls.md).
11. If you add a setting, add the field to `src/ragassist/shared/config/settings.py` and update `.env.example` in the same
    change. Give a required value no default.
12. Write the tests:

    - A unit test of the use case in `tests/unit/` with the in-memory adapter.
    - A security test. The test `tests/security/test_route_auth_sweep.py` checks every route that is not public. It sends
      bad tokens and expects 401 or 403. A new route is covered by it with no change.
    - If the route is **public**, add it to `PUBLIC_EXACT` in that file. Do this only when it must be public.
    - An HTTP-level test in `tests/e2e/` or an integration test if the route touches the database.

13. Check the layers:

    ```bash
    lint-imports
    pytest tests/hygiene/test_architecture.py
    ```

14. Update the API files. See [regenerate API types and OpenAPI](regenerate-api-types-and-openapi.md). If the route
    sends live events, also update `docs/api/sse-contract.md`.
15. If the change alters the architecture, add or update an ADR in `docs/adr/`. Also update
    [the API endpoints reference](../reference/api-endpoints.md).

## Check

- `pytest tests/unit tests/security` passes. See [run the tests](run-the-tests.md).
- `lint-imports` exits with 0.
- The new route appears at `/docs` of the API (a local address, not through the web proxy) and in
  `docs/api/openapi.json`.
- A request with no token gets 401 and a token with the wrong role gets 403.

## Troubleshooting

- `lint-imports` fails. An inner layer imports an outer one. Move the import or add a port.
- The route returns 404 in the browser but works on the API. The web proxy in
  `infra/nginx/templates/default.conf.template` forwards the path prefix `/v1/` and the exact path `/healthz`. A route
  outside `API_V1_PREFIX` does not pass. Keep new routes under `/v1/`. The proxy does not forward `/docs`.
- A sweep test fails with 200 for a bad token. The route does not use `get_current_principal`.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Components of the API](../c4/03-components-api.md)
- [Roles and permissions](../reference/roles-and-permissions.md)
- [ADR 0006: conversation access and approval binding](../adr/0006-conversation-access-and-approval-binding.md)
