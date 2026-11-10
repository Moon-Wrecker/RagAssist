# Rotate secrets and use the secret guards

**Type:** How-to · **Audience:** a developer or operator who owns the secrets of a deployment · **Verified against:** `a989287`

**In plain English:** This page has two jobs. First, it shows how to turn on the guards that stop a secret from
reaching the remote repository. Second, it shows how to replace a secret (rotate it) when it changed or leaked. The
rule is simple: a secret lives in `.env` only, and a secret that was ever pushed is leaked.

## Goal

Keep secrets out of git. Replace a secret safely when you must.

## Before you start

- You know the rule from `AGENTS.md`, sections 3.7 and 3.8. No password, key, token or deployment value goes in code,
  tests, compose files, docs or history.
- You know where values live: the git-ignored `.env` (or the secret store of the deployment). The template
  `.env.example` holds blank secrets.
- You can open the repository on the machine that you use for commits.

## Part A: turn on the secret guards

The repository has four layers. This part sets up the first one.

1. Open a terminal in the root folder of the repository.
2. Point git at the hook folder:

   ```bash
   git config core.hooksPath .githooks
   ```

   Do this once for each clone.

3. Know what the hooks do. The hook `.githooks/pre-commit` runs `scripts/check_secrets.py --staged`. The hook
   `.githooks/pre-push` runs `scripts/check_secrets.py --push`.

   > **WARNING.** Never use `git commit --no-verify` or `git push --no-verify`. The option skips the guard and a secret
   > can reach the remote.

4. Run the scanner by hand when you want to check:

   ```bash
   python scripts/check_secrets.py --all
   ```

   | Mode | What it scans |
   |---|---|
   | `--staged` | The lines that you staged |
   | `--push` | The commits that you are about to push |
   | `--range A..B` | The commits in a range, for example a pull request |
   | `--all` | The whole tree |

   The exit code is 0 when the scan is clean, 1 when it finds a secret and 2 for a usage error or a git error. A finding
   shows only the first four characters of the value.

5. Know the other three layers: the CI job `lint-and-typecheck` runs the scanner over the whole tree and over each
   commit of a pull request, a test in `tests/hygiene/test_no_secrets_committed.py` runs in the unit run, and GitHub push
   protection rejects known provider keys on the server.

The scanner reads the **added lines of every commit**. A key that you added and then removed is still found.

A line may carry the marker `secret-scan: allow`. Use it only for a documented value that is not a secret.

## Part B: rotate a secret

### First: if the secret leaked

> **WARNING.** A secret that was pushed even once is leaked. Rotate it **first**. Only then purge it from the git
> history. A purge alone does not make the old value safe.

### Rotate a provider key

1. Create a new key in the console of the provider. Revoke the old key there.
2. Put the new value in `.env`, for example in `OPENAI_API_KEY`.
3. Recreate the containers that use it:

   ```bash
   docker compose up -d --force-recreate api worker
   ```

### Rotate `SECRET_KEY` (the JWT signing key)

> **CAUTION.** The change makes every access token invalid at once. Signed-in users get new tokens when the browser
> refreshes. Refresh tokens are opaque values in the database, so they stay valid.

1. Generate a new random value on your machine. Do not paste it into a chat or a document.
2. Put it in `.env` as `SECRET_KEY`.
3. Recreate the three containers that read it. Compose also gives `SECRET_KEY` and `JWT_ALGORITHM` to `mock-saas`:

   ```bash
   docker compose up -d --force-recreate api worker mock-saas
   ```

### Rotate `DEV_AUTH_SECRET`

1. Put a new random value in `.env`.
2. Recreate the API: `docker compose up -d --force-recreate api`.

### Rotate a database password

> **WARNING.** The roles are created once, on a fresh data volume, by `infra/postgres/create-app-role.sh`. A new value in
> `.env` does **not** change the role in an existing database. If you change `.env` only, the API cannot connect.

1. Open a `psql` session as the owner role. For example run
   `docker compose exec postgres psql -U <DB_ADMIN_USER> -d <database>`. Unverified: the author did not check the
   authentication path of the local socket.
2. Run `\password <DB_APP_USER>` and type the new password. The `\password` command asks for the value, so the
   value is not in the shell history.
3. Repeat for `<DB_ADMIN_USER>` if you rotate that password too.
4. Put the same new values in `.env` as `DB_APP_PASSWORD` and `DB_ADMIN_PASSWORD`.
5. Recreate the containers: `docker compose up -d --force-recreate migrate api worker`.

> **CAUTION.** Do not use `ragassist init-env --force` to rotate. It replaces the whole file with no backup. It makes new
> database passwords that do not match the existing volume.

## Check

- `python scripts/check_secrets.py --all` exits with 0.
- `git config core.hooksPath` prints `.githooks`.
- After a rotation, `docker compose ps` shows `api` as `healthy` and a sign-in works.
- The old secret no longer works at the provider or at the database.

## Troubleshooting

- A commit is blocked. The scanner found a secret-shaped value. Remove it from the staged lines. Put it in `.env`.
- The hooks do not run. Check `git config core.hooksPath`. On Windows, a CRLF line ending in a hook script breaks the
  shebang. `.gitattributes` keeps shell scripts at LF.
- The API cannot connect after a password change. The role in the database and `.env` differ. See the database steps.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Security controls](../reference/security-controls.md)
- [CI and quality gates](../reference/ci-and-quality-gates.md)
- [Configuration reference](../reference/configuration.md)
