# Regenerate API types and OpenAPI

**Type:** How-to · **Audience:** a developer who changed an API route or a schema · **Verified against:** `a989287`

**In plain English:** The API describes itself in the file `docs/api/openapi.json`. The web app builds its TypeScript types
from that file. When you change a route, you must refresh both files, or the CI drift check fails. This page shows how.

## Goal

Make `docs/api/openapi.json` and `frontend/src/api/schema.d.ts` match the current code.

## Before you start

- You changed a route, a request model or a response model.
- You work from the **root of the repository**, with the virtual environment active and a valid `.env` in place. Importing the
  app reads the settings, so a required value that is missing stops the command.
- Node 22 is installed and `npm ci` ran in `frontend/`.
- No committed script makes the OpenAPI file. The one-line command below does it. The author checked that it reproduces the
  committed file byte for byte at this commit.

## Steps

1. Write the OpenAPI file from the app. Run this command from the repository root:

   ```bash
   python -c "import json, pathlib; from ragassist.main import app; pathlib.Path('docs/api/openapi.json').write_text(json.dumps(app.openapi(), indent=2) + chr(10), encoding='utf-8', newline='\n')"
   ```

   The file uses two spaces of indent, UTF-8 and a final newline with LF line endings. Keep these, or the diff shows noise.

2. Look at the change:

   ```bash
   git diff docs/api/openapi.json
   ```

   Check that the diff shows only the change that you made.

3. Move to the frontend folder:

   ```bash
   cd frontend
   ```

4. Regenerate the types:

   ```bash
   npm run api:types
   ```

   The script runs `openapi-typescript ../docs/api/openapi.json -o src/api/schema.d.ts`.

5. Run the drift check:

   ```bash
   npm run api:check
   ```

   It prints `API types are in sync with docs/api/openapi.json.` when both files match.

6. Run the type check, because a changed type can break the code that uses it:

   ```bash
   npm run typecheck
   ```

7. If the change touches the live event stream, update `docs/api/sse-contract.md` by hand. The OpenAPI file does not describe
   events. Also update the [API endpoints reference](../reference/api-endpoints.md).
8. Commit the two generated files together with the code change.

## Check

- `npm run api:check` exits with 0.
- `npm run typecheck` exits with 0.
- Your new route is in `docs/api/openapi.json`.

## Troubleshooting

- The command stops with a settings error. A required value is missing from `.env`. Run `ragassist init-env` for a new file.
  Do not copy `.env` into a document or a commit.
- The command prints the error "A path prefix must start with '/'". The value of `API_V1_PREFIX` does not start with `/`.
  Check the value in `.env` and in the environment of your shell. Unverified cause: Git Bash on Windows can rewrite a
  value such as `/v1` into a Windows path when you export it. Keep the value in `.env` and do not export it.
- The diff touches many lines that you did not change. The line endings or the indent differ. Use the exact command above.
- `api:check` fails in CI but passes for you. You did not commit `src/api/schema.d.ts`, or CRLF line endings changed it.
  The check normalizes CRLF, so look for a real content difference.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Develop the frontend](develop-the-frontend.md)
- [Add an API endpoint](add-an-api-endpoint.md)
- [The SSE contract](../api/sse-contract.md)
