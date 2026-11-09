"""Initial schema: tenants, knowledge, conversations (with escalation ticket) and audit, under row-level security.

Revision ID: 0001
Revises:

Design notes (ADR 0001 / 0002):
* Every tenant-scoped table carries ``tenant_id`` and has row-level security enabled. The policy compares it with
  ``current_setting('app.tenant_id')``, which ``UnitOfWork`` sets with ``set_config(..., is_local => true)``.
* ``documents`` and ``chunks`` may hold *global* rows (``tenant_id IS NULL``): readable by every tenant, writable
  only by the owner role (the seed command), never by the application role.
* The application role (``app_user``) is not the table owner and has no BYPASSRLS, so the policies bind it.
* The LangGraph checkpoint tables are created by ``AsyncPostgresSaver.setup()`` (``ragassist db upgrade``); they are
  guarded by the namespaced ``{tenant_id}:{conversation_id}`` thread id and the ``conversations`` ownership check.
* One statement per ``op.execute`` call: asyncpg cannot prepare several commands at once.
"""

import re

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CURRENT_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

TENANT_TABLES_FULL_ACCESS = (
    "users",
    "ingestion_jobs",
    "conversations",
    "messages",
    "tool_audit_log",
)
TENANT_TABLES_WITH_GLOBAL_READ = ("documents", "chunks")

TABLES = [
    """
    CREATE TABLE tenants (
        id uuid PRIMARY KEY,
        name varchar(255) NOT NULL,
        slug varchar(100) NOT NULL UNIQUE,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE users (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        email varchar(255) NOT NULL,
        role varchar(50) NOT NULL DEFAULT 'user',
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_users_tenant_id ON users (tenant_id)",
    "CREATE INDEX ix_users_email ON users (email)",
    """
    CREATE TABLE documents (
        id uuid PRIMARY KEY,
        tenant_id uuid,
        title varchar(512) NOT NULL,
        filename varchar(512) NOT NULL,
        content_type varchar(100) NOT NULL,
        file_size_bytes bigint NOT NULL DEFAULT 0,
        object_key text NOT NULL,
        content_hash varchar(64) NOT NULL DEFAULT '',
        status varchar(20) NOT NULL DEFAULT 'queued',
        error_message text,
        created_by uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_documents_tenant_id ON documents (tenant_id, created_at DESC)",
    # The upload use case inserts the job before the document inside one transaction, so the foreign key is
    # deferred to commit time.
    """
    CREATE TABLE ingestion_jobs (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL,
        document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        status varchar(20) NOT NULL DEFAULT 'queued',
        attempts integer NOT NULL DEFAULT 0,
        chunks_created integer NOT NULL DEFAULT 0,
        tokens_indexed integer NOT NULL DEFAULT 0,
        error_message text,
        started_at timestamptz,
        completed_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_ingestion_jobs_document ON ingestion_jobs (document_id)",
    "CREATE INDEX ix_ingestion_jobs_tenant ON ingestion_jobs (tenant_id)",
    """
    CREATE TABLE chunks (
        id varchar(64) PRIMARY KEY,
        tenant_id uuid,
        document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        text text NOT NULL,
        embed_text text,
        heading_path jsonb DEFAULT '[]'::jsonb,
        page integer,
        title varchar(255) DEFAULT '',
        embedding vector(1536),
        fts tsvector,
        chunk_index integer,
        token_count integer,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_chunks_tenant_id ON chunks (tenant_id)",
    "CREATE INDEX ix_chunks_document_id ON chunks (document_id)",
    "CREATE INDEX ix_chunks_fts ON chunks USING gin (fts)",
    "CREATE INDEX ix_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)",
    """
    CREATE TABLE conversations (
        tenant_id uuid NOT NULL,
        id varchar(100) NOT NULL,
        user_id uuid,
        title varchar(255) NOT NULL DEFAULT 'New Conversation',
        status varchar(30) NOT NULL DEFAULT 'open',
        ticket_id varchar(100),
        priority varchar(20),
        summary text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, id)
    )
    """,
    """
    CREATE TABLE messages (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL,
        conversation_id varchar(100) NOT NULL,
        role varchar(20) NOT NULL,
        text text NOT NULL,
        citations jsonb NOT NULL DEFAULT '[]'::jsonb,
        user_id uuid,
        route varchar(40),
        model_used varchar(120),
        decider_used varchar(60),
        created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_messages_conversation ON messages (tenant_id, conversation_id, created_at)",
    """
    CREATE TABLE tool_audit_log (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL,
        conversation_id varchar(100),
        user_id uuid,
        tool varchar(100) NOT NULL,
        arguments jsonb NOT NULL DEFAULT '{}'::jsonb,
        result jsonb,
        status varchar(20) NOT NULL,
        approver_id uuid,
        reason text,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_tool_audit_log_tenant ON tool_audit_log (tenant_id, created_at DESC)",
]


def _policies() -> list[str]:
    statements: list[str] = []
    for table in TENANT_TABLES_FULL_ACCESS:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"CREATE POLICY {table}_tenant_isolation ON {table} FOR ALL "
            f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})",
        ]
    for table in TENANT_TABLES_WITH_GLOBAL_READ:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"CREATE POLICY {table}_read ON {table} FOR SELECT "
            f"USING (tenant_id IS NULL OR tenant_id = {CURRENT_TENANT})",
            f"CREATE POLICY {table}_write ON {table} FOR ALL "
            f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})",
        ]
    return statements


def _grants() -> str:
    """Grant the application role access to what exists now (default privileges cover later tables)."""
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
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for statement in TABLES:
        op.execute(statement)
    for statement in _policies():
        op.execute(statement)
    op.execute(_grants())


def downgrade() -> None:
    for table in ("tool_audit_log", "messages", "conversations", "chunks", "ingestion_jobs", "documents", "users", "tenants"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
