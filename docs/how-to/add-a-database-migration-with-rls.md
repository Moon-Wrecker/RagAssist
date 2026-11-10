# Add a database migration with row-level security

**Type:** How-to · **Audience:** a developer who adds or changes a table · **Verified against:** `a989287`

**In plain English:** This page shows how to add a new table that holds data of one workspace. The table must have
row-level security (RLS), so that the database itself stops one workspace from reading the rows of another. You write the
migration by hand in plain SQL and you prove the protection with a test.

## Goal

Add a tenant-scoped table with RLS that the database enforces, with a migration that goes up and down.

## Before you start

- You know the terms [RLS](../glossary.md), [FORCE RLS](../glossary.md) and [Alembic](../glossary.md).
- You read [ADR 0002: row-level security](../adr/0002-row-level-security.md) and the
  [data model](../reference/data-model.md).
- The database runs, and `.env` is present. The migration tool reads `DATABASE_ADMIN_URL` (the owner role).
- You work from the **root of the repository**. The file `alembic.ini` and the folder `migrations/` are there.

> **WARNING.** A table with a `tenant_id` column and no policy leaks data between workspaces. Never skip the policy
> statements. Never give the application role the owner role or the `BYPASSRLS` attribute.

## Steps

1. Choose the next revision number. The existing revisions are `0001` and `0002`, so the next one is `0003`.
2. Make the file. The project writes SQL by hand and does not use autogenerate:

   ```bash
   alembic revision -m "add notes" --rev-id 0003
   ```

   The file name pattern is `<rev>_<slug>.py`, so you get `migrations/versions/0003_add_notes.py`. The template is
   `migrations/script.py.mako`.

3. Set `down_revision = "0002"` in the new file.
4. Write the table as plain SQL strings. The table `notes` is an invented example:

   ```python
   CURRENT_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

   STATEMENTS = [
       """
       CREATE TABLE notes (
           id uuid PRIMARY KEY,
           tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
           body text NOT NULL,
           created_at timestamptz NOT NULL DEFAULT now()
       )
       """,
       "CREATE INDEX ix_notes_tenant ON notes (tenant_id, created_at DESC)",
   ]
   ```

5. Add the three RLS statements for the table. Keep one statement for each `op.execute` call:

   ```python
   POLICIES = [
       "ALTER TABLE notes ENABLE ROW LEVEL SECURITY",
       "ALTER TABLE notes FORCE ROW LEVEL SECURITY",
       "CREATE POLICY notes_tenant_isolation ON notes FOR ALL "
       f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})",
   ]
   ```

   `FORCE` makes the rule apply even to the owner of the table. The policy name is `<table>_tenant_isolation`.

6. Copy the `_grants()` function from `migrations/versions/0002_accounts_sessions_invites.py`. It grants the privileges to
   the application role. It reads the role name from `DB_APP_USER` and accepts only a plain SQL identifier.
7. Write `upgrade()`. Run the table statements, then the policies, then the grants:

   ```python
   def upgrade() -> None:
       for statement in STATEMENTS:
           op.execute(statement)
       for statement in POLICIES:
           op.execute(statement)
       op.execute(_grants())
   ```

8. Write `downgrade()`. It must undo the change:

   ```python
   def downgrade() -> None:
       op.execute("DROP TABLE IF EXISTS notes CASCADE")
   ```

9. Know the other pattern. A table with shared rows (`tenant_id` is null) that every workspace may **read** uses two
   policies, named `<table>_read` and `<table>_write`. The read policy also shows rows that have no tenant. The write
   policy allows only the rows of the current tenant. See `migrations/versions/0001_initial_schema.py`.
10. Apply the migration:

    ```bash
    ragassist db upgrade
    ```

    The command runs Alembic to `head`, then sets up the LangGraph checkpoint tables, then runs the grants.

11. Write the code that uses the table. Open the table only through a tenant scope. The Postgres repositories use
    `ScopedDatabase.scope(tenant_id)` from `src/ragassist/shared/db/scoped.py`. It runs
    `set_config('app.tenant_id', :tid, true)` inside a transaction. `UnitOfWork` in `src/ragassist/shared/db/uow.py`
    does the same and refuses a session with an open transaction.
12. Take `tenant_id` from the signed-in `Principal` only. Never take it from the request body, a model output or a tool
    argument.
13. Add the test. In `tests/integration/test_rls_and_uow.py`, the set `COVERED_TABLES` lists the tables that the isolation
    matrix proves. The test `test_every_tenant_scoped_table_has_matrix_coverage` fails when a table with a `tenant_id`
    column is in the SQLAlchemy metadata and not in the set. Add your table name there if you declare an ORM model. The
    forced-RLS test and the policy-exists test read the same ORM list, so they cover your table too.

    Unverified: the matrix lists tables from the SQLAlchemy `Base.metadata`. A table that you create only with SQL is not
    found by that check. Add the forced-RLS check and the policy-exists check for it by hand in the same file.

14. If a Docker image holds the migrations, rebuild it. The image copies `migrations/` at build time:

    ```bash
    docker compose up -d --build migrate api worker
    ```

## Check

- `ragassist db upgrade` ends with no error.
- In `psql`, `\d+ notes` shows "Policies" and "Row security: enabled, forced".
- `pytest tests/integration/test_rls_and_uow.py` passes. See [run the tests](run-the-tests.md).
- `ragassist db upgrade` run a second time changes nothing.

## Troubleshooting

- The app role gets "permission denied for table". The `_grants()` call is missing, or `DB_APP_USER` does not name an
  existing role.
- The migration runs on the wrong database. `migrations/env.py` reads `DATABASE_ADMIN_URL`. Check `.env`.
- The test refuses to run. The integration database name must contain `test`, or `RAGASSIST_TEST_DB_ALLOW_WIPE=1` must be
  set for a database that you may erase.
- More help: [troubleshoot common problems](troubleshoot-common-problems.md).

## Related pages

- [Data model](../reference/data-model.md)
- [Security controls](../reference/security-controls.md)
- [Command-line reference](../reference/cli.md)
