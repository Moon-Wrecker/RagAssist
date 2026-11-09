"""Accounts: passwords and status on users, refresh sessions, invite and reset links, workspace slug lookup.

Revision ID: 0002
Revises: 0001

Design notes (ADR 0007):
* ``users`` gains ``password_hash`` (argon2id, NULL until the person sets one through an invite or reset link),
  ``status`` (``active`` or ``disabled``) and a unique ``(tenant_id, lower(email))``, so an address names one
  account per workspace.
* ``auth_sessions`` holds one row per refresh token. Only the SHA-256 of the random part is stored. Rows of one
  login share a ``family_id``; presenting a token that was already rotated revokes the whole family.
* ``invites`` holds one-time links (``kind`` = ``invite`` for a new account, ``reset`` for an existing one).
* Both tables sit under the same row-level security as every tenant table.
* Sign-in knows a workspace slug before it knows a tenant id. Rather than a ``SECURITY DEFINER`` function (which
  ``FORCE ROW LEVEL SECURITY`` would still bind), ``tenants`` gets one extra read policy that exposes exactly the
  row whose slug equals the transaction-local ``app.tenant_slug``. The application sets that for the lookup and
  nothing else, so a caller still cannot list workspaces.
* One statement per ``op.execute`` call: asyncpg cannot prepare several commands at once.
"""

import re

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CURRENT_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
CURRENT_SLUG = "NULLIF(current_setting('app.tenant_slug', true), '')"

NEW_TABLES = ("auth_sessions", "invites")

STATEMENTS = [
    "ALTER TABLE users ADD COLUMN password_hash text",
    "ALTER TABLE users ADD COLUMN status varchar(20) NOT NULL DEFAULT 'active'",
    "ALTER TABLE users ADD CONSTRAINT ck_users_status CHECK (status IN ('active', 'disabled'))",
    "CREATE UNIQUE INDEX uq_users_tenant_email ON users (tenant_id, lower(email))",
    """
    CREATE TABLE auth_sessions (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        family_id uuid NOT NULL,
        token_hash char(64) NOT NULL,
        expires_at timestamptz NOT NULL,
        rotated_at timestamptz,
        revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX uq_auth_sessions_token_hash ON auth_sessions (token_hash)",
    "CREATE INDEX ix_auth_sessions_user ON auth_sessions (tenant_id, user_id)",
    "CREATE INDEX ix_auth_sessions_family ON auth_sessions (family_id)",
    """
    CREATE TABLE invites (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        kind varchar(10) NOT NULL CHECK (kind IN ('invite', 'reset')),
        email varchar(255) NOT NULL,
        role varchar(50) NOT NULL DEFAULT 'user',
        user_id uuid REFERENCES users(id) ON DELETE CASCADE,
        token_hash char(64) NOT NULL,
        created_by uuid,
        expires_at timestamptz NOT NULL,
        accepted_at timestamptz,
        revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX uq_invites_token_hash ON invites (token_hash)",
    "CREATE INDEX ix_invites_tenant ON invites (tenant_id, created_at DESC)",
    # One pending invite per address per workspace (resend = revoke the old one first).
    "CREATE UNIQUE INDEX uq_invites_pending_email ON invites (tenant_id, lower(email)) "
    "WHERE kind = 'invite' AND accepted_at IS NULL AND revoked_at IS NULL",
]


def _policies() -> list[str]:
    statements = [
        f"CREATE POLICY tenants_slug_lookup ON tenants FOR SELECT USING (slug = {CURRENT_SLUG})",
    ]
    for table in NEW_TABLES:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL "
            f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})",
        ]
    return statements


def _grants() -> str:
    from ragassist.shared.config.settings import get_settings

    role = get_settings().DB_APP_USER
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError("DB_APP_USER must be a plain SQL identifier")
    return f"""
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
        GRANT ALL ON ALL TABLES IN SCHEMA public TO {role};
        GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {role};
    END IF;
END
$$
"""


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for statement in _policies():
        op.execute(statement)
    op.execute(_grants())


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenants_slug_lookup ON tenants")
    for table in NEW_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP INDEX IF EXISTS uq_users_tenant_email")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_status")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash")
