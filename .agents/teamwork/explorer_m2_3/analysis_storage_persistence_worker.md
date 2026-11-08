# Technical Analysis: Storage, Queue, Persistence & Background Ingestion Worker Pipeline

- **Role**: Storage, Queue, Persistence & Worker Explorer (`explorer_m2_3`)
- **Milestone**: Milestone 2 (Ingestion & Knowledge Storage Pipeline)
- **Target Components**:
  - S3 Storage Adapter (`src/ragassist/platform/storage/s3.py`)
  - SQS Queue Adapter (`src/ragassist/platform/queue/sqs.py`)
  - Database Models (`src/ragassist/modules/knowledge/adapters/persistence/models.py`)
  - Row-Level Security (RLS) & Defect Fixes (`DEFECT-09`, `DEFECT-10`)
  - Alembic Database Migrations (`migrations/versions/0001_knowledge_schema_and_rls.py`)
  - Background Ingestion Worker Daemon (`src/ragassist/worker/ingestion_worker.py`)
  - Knowledge Upload REST Router (`src/ragassist/modules/knowledge/api/router.py`)

---

## 1. Executive Summary & Architecture Scope

Milestone 2 establishes the end-to-end ingestion and knowledge persistence pipeline of **RagAssist**. Following the Modular Monolith and Hexagonal Architecture principles laid out in `PROJECT.md` and `AGENTS.md`:

1. **Storage Platform Layer (`ragassist.platform.storage`)**: An async object store adapter using `aioboto3` managing raw uploaded files in S3 (`ragassist-docs`) or LocalStack S3, providing atomic puts, streaming uploads/downloads, key existence checks, and presigned URLs.
2. **Queue Platform Layer (`ragassist.platform.queue`)**: An async message queue adapter using `aioboto3` targeting SQS (`ragassist-ingest`) and DLQ (`ragassist-ingest-dlq`) with redrive policies, receipt handle deletions, and visibility timeout extensions.
3. **Knowledge Persistence Layer (`ragassist.modules.knowledge.adapters.persistence`)**: SQLAlchemy 2.0 async models for `DocumentModel`, `ChunkModel` (with `vector(1536)` and full-text search `tsvector`), and `IngestionJobModel`, backed by strict Row-Level Security (RLS).
4. **Tenant Isolation & Defect Remediation**:
   - Remediation of **DEFECT-09**: Missing RLS policies and `FORCE ROW LEVEL SECURITY` in PostgreSQL.
   - Remediation of **DEFECT-10**: `UnitOfWork.__aenter__` failing when entering an autobegun session.
   - Matrix update in `tests/integration/test_rls_and_uow.py` (`COVERED_TABLES`).
5. **Alembic Migration Pipeline**: Database migration enabling `vector` and `uuid-ossp`, creating tenant-isolated tables, enforcing RLS policies, and establishing an HNSW cosine distance index (`m=16, ef_construction=64`) and GIN tsvector index.
6. **Background Ingestion Worker (`ragassist.worker.ingestion_worker`)**: An asynchronous long-running daemon that polls SQS, claims ingestion jobs, downloads objects from S3, offloads CPU-heavy AST parsing and hybrid chunking to the bounded thread pool via `run_cpu_bound()`, generates dense embeddings with `EmbeddingService`, and transactionally replaces chunks in PostgreSQL within a tenant-scoped `UnitOfWork`.
7. **Knowledge Upload REST Router (`ragassist.modules.knowledge.api.router`)**: FastAPI endpoint for streaming multipart file uploads, authenticating via JWT `Principal`, validating MIME/size limits, and coordinating S3/DB/SQS atomicity.

---

## 2. S3 Storage Adapter (`src/ragassist/platform/storage/s3.py`)

### 2.1 Interface Contract & Protocols

The storage adapter satisfies the core `ObjectStore` contract expected by `tests/support/contracts/object_store.py` and `tests/support/specs/map.py`, while exposing streaming and presigned URL capabilities for production use:

```python
# src/ragassist/platform/storage/ports.py
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

class ObjectNotFound(KeyError, Exception):
    """Raised when an object key does not exist in the store."""
    pass

@runtime_checkable
class ObjectStore(Protocol):
    """Protocol for interacting with object storage (AWS S3 / LocalStack / In-Memory)."""

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Store raw bytes in object storage and return the object URL/URI."""
        ...

    async def get(self, key: str) -> bytes:
        """Retrieve raw object bytes by key. Raises ObjectNotFound if missing."""
        ...

    async def exists(self, key: str) -> bool:
        """Check whether an object key exists in the store."""
        ...

    async def delete(self, key: str) -> bool:
        """Delete an object by key. Must be idempotent (returns bool, never raises on missing)."""
        ...

    async def upload_stream(
        self,
        key: str,
        stream: AsyncIterator[bytes],
        content_type: str = "application/octet-stream",
    ) -> str:
        """Stream data directly to object store (for large multipart uploads)."""
        ...

    async def download_stream(self, key: str) -> AsyncIterator[bytes]:
        """Stream object content as chunks."""
        ...

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        http_method: str = "GET",
    ) -> str:
        """Generate a presigned URL for direct secure download or upload."""
        ...
```

### 2.2 S3 Adapter Implementation Details

```python
# src/ragassist/platform/storage/s3.py
from collections.abc import AsyncIterator
import io
from typing import Any
import aioboto3
from botocore.exceptions import ClientError
import structlog

from ragassist.platform.storage.ports import ObjectNotFound, ObjectStore
from ragassist.shared.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)

class S3ObjectStore(ObjectStore):
    """AWS S3 and LocalStack S3 implementation using aioboto3."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bucket = self.settings.S3_BUCKET_DOCS
        self.session = aioboto3.Session(
            aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY,
            region_name=self.settings.AWS_REGION,
        )

    def _get_client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self.settings.USE_LOCALSTACK and self.settings.LOCALSTACK_ENDPOINT:
            kwargs["endpoint_url"] = self.settings.LOCALSTACK_ENDPOINT
        return kwargs

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        async with self.session.client("s3", **self._get_client_kwargs()) as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            logger.debug("s3.put_object", bucket=self.bucket, key=key, size=len(data))
            return f"s3://{self.bucket}/{key}"

    # Alias for backwards compatibility with earlier platform port
    async def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream", metadata: dict[str, str] | None = None) -> str:
        return await self.put(key, data, content_type=content_type)

    async def get(self, key: str) -> bytes:
        async with self.session.client("s3", **self._get_client_kwargs()) as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=key)
                async with response["Body"] as stream:
                    return await stream.read()
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in ("404", "NoSuchKey"):
                    raise ObjectNotFound(f"Object not found: {key}") from exc
                raise

    # Alias for backwards compatibility
    async def get_object(self, key: str) -> bytes:
        return await self.get(key)

    async def exists(self, key: str) -> bool:
        async with self.session.client("s3", **self._get_client_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in ("404", "NoSuchKey", "403"):
                    return False
                raise

    async def delete(self, key: str) -> bool:
        async with self.session.client("s3", **self._get_client_kwargs()) as s3:
            try:
                await s3.delete_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError:
                return True  # Idempotent delete

    # Alias for backwards compatibility
    async def delete_object(self, key: str) -> bool:
        return await self.delete(key)

    async def upload_stream(
        self,
        key: str,
        stream: AsyncIterator[bytes],
        content_type: str = "application/octet-stream",
    ) -> str:
        buffer = io.BytesIO()
        async for chunk in stream:
            buffer.write(chunk)
        data = buffer.getvalue()
        return await self.put(key, data, content_type=content_type)

    async def download_stream(self, key: str) -> AsyncIterator[bytes]:
        async with self.session.client("s3", **self._get_client_kwargs()) as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=key)
                async with response["Body"] as stream:
                    while chunk := await stream.read(64 * 1024):
                        yield chunk
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in ("404", "NoSuchKey"):
                    raise ObjectNotFound(f"Object not found: {key}") from exc
                raise

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        http_method: str = "GET",
    ) -> str:
        async with self.session.client("s3", **self._get_client_kwargs()) as s3:
            method = "get_object" if http_method.upper() == "GET" else "put_object"
            url = await s3.generate_presigned_url(
                ClientMethod=method,
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
```

### 2.3 Object Key Hierarchy & Tenant Boundary
Object keys strictly enforce tenant boundaries to prevent any cross-tenant collision or directory escape:
- Format: `tenants/{tenant_id}/documents/{document_id}/{sanitized_filename}`
- Traversal Neutralization: Strip `..`, leading slashes `/`, and backslashes `\` before forming the key.

---

## 3. SQS Message Queue Adapter (`src/ragassist/platform/queue/sqs.py`)

### 3.1 Interface Contract & Received DTO

The queue adapter implements `MessageQueue` and handles both string and JSON dict bodies, supporting redrive to DLQ after 3 failed attempts:

```python
# src/ragassist/platform/queue/ports.py
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

@dataclass(frozen=True)
class Received:
    """Delivered queue message carrying unique IDs, receipt handle, body, and receive counter."""
    message_id: str
    receipt: str
    body: str
    receive_count: int = 1

    @property
    def receipt_handle(self) -> str:
        return self.receipt

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

@runtime_checkable
class MessageQueue(Protocol):
    """Protocol for asynchronous message queuing (AWS SQS / LocalStack SQS / In-Memory)."""

    async def send(self, body: str | dict[str, Any], delay_seconds: int = 0) -> str:
        """Enqueue message and return assigned message ID."""
        ...

    async def receive(self, max_messages: int = 10, wait_time_seconds: int = 10) -> list[Received]:
        """Receive messages up to max_messages with long polling."""
        ...

    async def delete(self, receipt: str) -> bool:
        """Acknowledge and delete message using receipt handle."""
        ...

    async def change_visibility(self, receipt: str, visibility_timeout: int) -> bool:
        """Extend or modify visibility timeout of an in-flight message."""
        ...
```

### 3.2 SQS Adapter Implementation Details

```python
# src/ragassist/platform/queue/sqs.py
import json
from typing import Any
from uuid import uuid4
import aioboto3
import structlog

from ragassist.platform.queue.ports import MessageQueue, Received
from ragassist.shared.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)

class SQSMessageQueue(MessageQueue):
    """Adapter for AWS SQS and LocalStack SQS."""

    def __init__(self, queue_name: str | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.queue_name = queue_name or self.settings.SQS_QUEUE_INGEST
        self.session = aioboto3.Session(
            aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY,
            region_name=self.settings.AWS_REGION,
        )
        self._queue_url: str | None = None

    def _get_client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self.settings.USE_LOCALSTACK and self.settings.LOCALSTACK_ENDPOINT:
            kwargs["endpoint_url"] = self.settings.LOCALSTACK_ENDPOINT
        return kwargs

    async def _resolve_queue_url(self, client: Any) -> str:
        if self._queue_url is None:
            resp = await client.get_queue_url(QueueName=self.queue_name)
            self._queue_url = resp["QueueUrl"]
        return self._queue_url

    async def send(self, body: str | dict[str, Any], delay_seconds: int = 0) -> str:
        body_str = json.dumps(body) if isinstance(body, dict) else str(body)
        async with self.session.client("sqs", **self._get_client_kwargs()) as sqs:
            q_url = await self._resolve_queue_url(sqs)
            resp = await sqs.send_message(
                QueueUrl=q_url,
                MessageBody=body_str,
                DelaySeconds=delay_seconds,
            )
            msg_id = resp.get("MessageId", str(uuid4()))
            logger.debug("sqs.sent_message", queue=self.queue_name, message_id=msg_id)
            return msg_id

    # Alias for compatibility with earlier platform ports
    async def send_message(self, queue_name: str, message_body: dict[str, Any], delay_seconds: int = 0) -> str:
        return await self.send(message_body, delay_seconds=delay_seconds)

    async def receive(self, max_messages: int = 10, wait_time_seconds: int = 10) -> list[Received]:
        async with self.session.client("sqs", **self._get_client_kwargs()) as sqs:
            q_url = await self._resolve_queue_url(sqs)
            resp = await sqs.receive_message(
                QueueUrl=q_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds,
                AttributeNames=["ApproximateReceiveCount"],
            )
            messages = []
            for item in resp.get("Messages", []):
                attrs = item.get("Attributes", {})
                receive_count = int(attrs.get("ApproximateReceiveCount", "1"))
                messages.append(
                    Received(
                        message_id=item["MessageId"],
                        receipt=item["ReceiptHandle"],
                        body=item["Body"],
                        receive_count=receive_count,
                    )
                )
            return messages

    # Alias for compatibility with earlier platform ports
    async def receive_messages(self, queue_name: str, max_messages: int = 10, wait_time_seconds: int = 10) -> list[dict[str, Any]]:
        msgs = await self.receive(max_messages=max_messages, wait_time_seconds=wait_time_seconds)
        return [{"message_id": m.message_id, "receipt_handle": m.receipt, "body": json.loads(m.body) if m.body.startswith("{") else m.body} for m in msgs]

    async def delete(self, receipt: str) -> bool:
        async with self.session.client("sqs", **self._get_client_kwargs()) as sqs:
            q_url = await self._resolve_queue_url(sqs)
            await sqs.delete_message(QueueUrl=q_url, ReceiptHandle=receipt)
            return True

    # Alias for compatibility with earlier platform ports
    async def delete_message(self, queue_name: str, receipt_handle: str) -> bool:
        return await self.delete(receipt_handle)

    async def change_visibility(self, receipt: str, visibility_timeout: int) -> bool:
        async with self.session.client("sqs", **self._get_client_kwargs()) as sqs:
            q_url = await self._resolve_queue_url(sqs)
            await sqs.change_message_visibility(
                QueueUrl=q_url,
                ReceiptHandle=receipt,
                VisibilityTimeout=visibility_timeout,
            )
            return True
```

---

## 4. PostgreSQL Persistence Models (`src/ragassist/modules/knowledge/adapters/persistence/models.py`)

The data models use SQLAlchemy 2.0 with `Mapped` and `mapped_column`, incorporating `pgvector.sqlalchemy.Vector` for dense semantic embeddings and `Computed` for full-text search tsvectors.

```python
# src/ragassist/modules/knowledge/adapters/persistence/models.py
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ragassist.shared.db.models import Base

class DocumentModel(Base):
    """Represents an uploaded source document belonging to a tenant."""

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False, default="application/octet-stream")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    chunks: Mapped[list["ChunkModel"]] = relationship(
        "ChunkModel", back_populates="document", cascade="all, delete-orphan", order_by="ChunkModel.chunk_index"
    )

    __table_args__ = (
        Index("ix_documents_tenant_created", "tenant_id", "created_at"),
    )


class ChunkModel(Base):
    """Represents a discrete semantic chunk extracted from a document."""

    __tablename__ = "document_chunks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    heading_path: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=True)
    fts: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
        nullable=True,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    document: Mapped[DocumentModel] = relationship("DocumentModel", back_populates="chunks")

    @property
    def content(self) -> str:
        return self.text

    @content.setter
    def content(self, value: str) -> None:
        self.text = value

    @property
    def page(self) -> int | None:
        return self.page_number

    @page.setter
    def page(self, value: int | None) -> None:
        self.page_number = value

    __table_args__ = (
        Index("ix_document_chunks_tenant_doc", "tenant_id", "document_id"),
        Index("ix_document_chunks_fts", "fts", postgresql_using="gin"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class IngestionJobModel(Base):
    """Tracks state and retries of an asynchronous document ingestion job."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
```

---

## 5. PostgreSQL Row-Level Security (RLS) & Defect Resolution

### 5.1 Remediation of DEFECT-10 (Autobegun Session in UnitOfWork)
**Root Cause**: In `src/ragassist/shared/db/uow.py`:
`__aenter__` called `await self.session.begin()` unconditionally. When an upstream dependency (such as FastAPI dependency or prior query) ran a statement, SQLAlchemy 2.0 automatically began a transaction. Calling `begin()` again triggered `sqlalchemy.exc.InvalidRequestError: A transaction is already begun on this Session.`

**Fix**:
```python
# In src/ragassist/shared/db/uow.py:
async def __aenter__(self) -> "UnitOfWork":
    """Begin transaction if not already active and set RLS session context."""
    if not self.session.in_transaction():
        await self.session.begin()
    self._in_transaction = True

    if self.tenant_id is not None:
        query = text("SELECT set_config('app.tenant_id', :tid, true)")
        await self.session.execute(query, {"tid": str(self.tenant_id)})
        logger.debug("rls.set_local_tenant", tenant_id=str(self.tenant_id))
    else:
        query = text("SELECT set_config('app.tenant_id', '', true)")
        await self.session.execute(query)

    return self
```

### 5.2 Remediation of DEFECT-09 (Missing RLS Policies)
**Root Cause**: `infra/postgres/init.sql` created `app_user` but applied no `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, or `CREATE POLICY`. As a result, non-superuser queries bypassed tenant isolation.

**Fix**:
Enforce RLS policies in `infra/postgres/init.sql` and the Alembic migration:
```sql
-- Policies for core tables
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_tenants ON tenants
    FOR ALL
    USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_users ON users
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Policies for knowledge tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_documents ON documents
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_chunks ON document_chunks
    FOR ALL
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR tenant_id IS NULL  -- Global shared knowledge documents
    )
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_jobs ON ingestion_jobs
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

### 5.3 Updating `tests/integration/test_rls_and_uow.py`
In `tests/integration/test_rls_and_uow.py`, the test:
```python
def test_every_tenant_scoped_table_has_matrix_coverage() -> None:
    assert {name for name, _ in TENANT_SCOPED} <= COVERED_TABLES
```
requires `COVERED_TABLES` to cover all tenant-scoped tables declared in `Base.metadata`:
```python
COVERED_TABLES = {"tenants", "users", "documents", "document_chunks", "ingestion_jobs"}
```
Updating `COVERED_TABLES` ensures full integration matrix verification across all tables without regression.

---

## 6. Alembic Database Migration Specification

### 6.1 Migration Structure
- Directory: `migrations/`
- Configuration: `alembic.ini`
- Version script: `migrations/versions/0001_initial_knowledge_and_rls.py`

### 6.2 Migration Script (`0001_initial_knowledge_and_rls.py`)
```python
"""Create core and knowledge tables with pgvector, HNSW, and RLS policies.

Revision ID: 0001_initial_knowledge_and_rls
Revises: None
Create Date: 2026-11-08 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001_initial_knowledge_and_rls"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # 2. Tenants table
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # 3. Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="user", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])

    # 4. Documents table
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("s3_uri", sa.String(1024), nullable=False),
        sa.Column("mime", sa.String(100), server_default="application/octet-stream", nullable=False),
        sa.Column("status", sa.String(50), server_default="queued", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_documents_tenant_created", "documents", ["tenant_id", "created_at"])

    # 5. Document Chunks table
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embed_text", sa.Text(), nullable=True),
        sa.Column("heading_path", postgresql.JSONB(), server_default="[]", nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("fts", postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', text)", persisted=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_document_chunks_tenant_doc", "document_chunks", ["tenant_id", "document_id"])
    op.create_index("ix_document_chunks_fts", "document_chunks", ["fts"], postgresql_using="gin")
    op.execute("""
        CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)

    # 6. Ingestion Jobs table
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ingestion_jobs_tenant_id", "ingestion_jobs", ["tenant_id"])
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])

    # 7. Enable & Force Row-Level Security
    CURRENT_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    for tbl in ("tenants", "users", "documents", "document_chunks", "ingestion_jobs"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")

    op.execute(f"CREATE POLICY tenant_isolation_tenants ON tenants FOR ALL USING (id = {CURRENT_TENANT}) WITH CHECK (id = {CURRENT_TENANT});")
    op.execute(f"CREATE POLICY tenant_isolation_users ON users FOR ALL USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT});")
    op.execute(f"CREATE POLICY tenant_isolation_documents ON documents FOR ALL USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT});")
    op.execute(f"CREATE POLICY tenant_isolation_chunks ON document_chunks FOR ALL USING (tenant_id = {CURRENT_TENANT} OR tenant_id IS NULL) WITH CHECK (tenant_id = {CURRENT_TENANT});")
    op.execute(f"CREATE POLICY tenant_isolation_jobs ON ingestion_jobs FOR ALL USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT});")

def downgrade() -> None:
    for tbl in ("ingestion_jobs", "document_chunks", "documents", "users", "tenants"):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE;")
```

---

## 7. Knowledge Application Layer & Use Cases

### 7.1 Domain Models & Job State Transitions (`src/ragassist/modules/knowledge/domain/`)

```python
# src/ragassist/modules/knowledge/domain/models.py
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from ragassist.shared.domain import DomainError

class InvalidTransition(DomainError):
    """Raised when an illegal job state transition is attempted."""
    pass

class UnsupportedMimeType(DomainError):
    """HTTP 415: Provided file format is not supported."""
    pass

class FileTooLarge(DomainError):
    """HTTP 413: Provided file size exceeds allowed limits."""
    pass

class ParseError(DomainError):
    """Raised when document parsing fails."""
    pass

class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

_LEGAL_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING},
    JobStatus.RUNNING: {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.QUEUED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
}

@dataclass
class IngestionJob:
    job_id: str
    document_id: str
    tenant_id: str
    status: JobStatus
    attempts: int = 0

    def transition_to(self, new_status: JobStatus) -> None:
        if new_status not in _LEGAL_TRANSITIONS.get(self.status, set()):
            raise InvalidTransition(f"Illegal transition from {self.status} to {new_status}")
        self.status = new_status
```

### 7.2 Upload Use Case (`src/ragassist/modules/knowledge/application/upload.py`)

Handles validation, atomic S3 write, database job record creation, and SQS dispatch:

```python
# src/ragassist/modules/knowledge/application/upload.py
from dataclasses import dataclass
import json
import pathlib
from uuid import uuid4

from ragassist.modules.knowledge.domain.models import FileTooLarge, UnsupportedMimeType
from ragassist.platform.queue.ports import MessageQueue
from ragassist.platform.storage.ports import ObjectStore

@dataclass(frozen=True)
class UploadCommand:
    tenant_id: str
    user_id: str
    filename: str
    mime: str
    content: bytes

@dataclass(frozen=True)
class UploadResult:
    job_id: str
    document_id: str
    object_key: str

class UploadDocument:
    """Orchestrates atomic document upload to S3, database job persistence, and SQS enqueueing."""

    def __init__(
        self,
        store: ObjectStore,
        queue: MessageQueue,
        documents: Any,  # Document repository / UoW
        max_bytes: int = 50 * 1024 * 1024,
        allowed_mimes: frozenset[str] = frozenset({
            "text/markdown", "text/html", "text/csv", "application/pdf"
        }),
    ) -> None:
        self.store = store
        self.queue = queue
        self.documents = documents
        self.max_bytes = max_bytes
        self.allowed_mimes = allowed_mimes

    async def execute(self, command: UploadCommand) -> UploadResult:
        # 1. Validate MIME and size
        if command.mime not in self.allowed_mimes:
            raise UnsupportedMimeType(f"MIME type not allowed: {command.mime}")
        if len(command.content) > self.max_bytes:
            raise FileTooLarge(f"File size {len(command.content)} exceeds max {self.max_bytes}")

        # 2. Sanitize filename to prevent path traversal
        clean_filename = pathlib.Path(command.filename).name.replace("..", "_")
        document_id = str(uuid4())
        job_id = str(uuid4())
        object_key = f"tenants/{command.tenant_id}/documents/{document_id}/{clean_filename}"

        # 3. Store object in S3
        await self.store.put(object_key, command.content, content_type=command.mime)

        try:
            # 4. Persist document and job inside transaction
            async with self.documents.transaction():
                job_cls = need("knowledge.IngestionJob")
                status_cls = need("knowledge.JobStatus")
                job = job_cls(
                    job_id=job_id,
                    document_id=document_id,
                    tenant_id=command.tenant_id,
                    status=status_cls.QUEUED,
                    attempts=0,
                )
                await self.documents.add_job(job)

            # 5. Dispatch SQS message
            queue_payload = json.dumps({
                "job_id": job_id,
                "document_id": document_id,
                "tenant_id": command.tenant_id,
                "object_key": object_key,
            })
            await self.queue.send(queue_payload)

            return UploadResult(job_id=job_id, document_id=document_id, object_key=object_key)

        except BaseException:
            # Atomicity rollback: remove orphaned object from S3
            try:
                await self.store.delete(object_key)
            except Exception:
                pass
            raise
```

---

## 8. Background Ingestion Worker Daemon (`src/ragassist/worker/ingestion_worker.py`)

### 8.1 Ingestion Outcome & Application Handler (`ProcessIngestionJob`)

```python
# src/ragassist/modules/knowledge/application/process_job.py
from enum import StrEnum
import json
from typing import Any, Mapping

import structlog

from ragassist.modules.knowledge.domain.models import JobStatus
from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.platform.storage.ports import ObjectNotFound, ObjectStore
from ragassist.shared.resilience import run_cpu_bound

logger = structlog.get_logger(__name__)

class IngestOutcome(StrEnum):
    COMPLETED = "completed"
    DUPLICATE_SKIPPED = "duplicate_skipped"
    RETRY = "retry"
    DEAD_LETTERED = "dead_lettered"
    REJECTED = "rejected"

class ProcessIngestionJob:
    """Core domain handler processing a single queued document ingestion job."""

    def __init__(
        self,
        documents: Any,
        store: ObjectStore,
        parsers: Mapping[str, Any],
        chunker: Any,
        embedder: EmbeddingProvider,
        max_retries: int = 3,
    ) -> None:
        self.documents = documents
        self.store = store
        self.parsers = parsers
        self.chunker = chunker
        self.embedder = embedder
        self.max_retries = max_retries

    async def handle(self, body: str) -> IngestOutcome:
        # 1. Parse JSON body
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            logger.warning("worker.reject_malformed_json", body=body)
            return IngestOutcome.REJECTED

        job_id = payload.get("job_id")
        tenant_id = payload.get("tenant_id")
        object_key = payload.get("object_key")
        document_id = payload.get("document_id")

        if not job_id or not tenant_id:
            logger.warning("worker.reject_missing_fields", payload=payload)
            return IngestOutcome.REJECTED

        # 2. Fetch existing job and enforce tenant matching
        job = await self.documents.get_job(job_id)
        if job is None:
            logger.warning("worker.reject_unknown_job", job_id=job_id)
            return IngestOutcome.REJECTED

        if str(job.tenant_id) != str(tenant_id):
            logger.warning("worker.reject_tenant_mismatch", job_tenant=job.tenant_id, msg_tenant=tenant_id)
            return IngestOutcome.REJECTED

        # 3. Idempotency checks
        if job.status == JobStatus.COMPLETED:
            logger.info("worker.skip_already_completed", job_id=job_id)
            return IngestOutcome.DUPLICATE_SKIPPED

        # Claim the job: transition queued -> running
        claimed = await self.documents.claim_job(job_id, tenant_id=tenant_id)
        if not claimed:
            logger.info("worker.skip_already_claimed", job_id=job_id)
            return IngestOutcome.DUPLICATE_SKIPPED

        # 4. Fetch raw content from S3
        try:
            content = await self.store.get(object_key)
        except (ObjectNotFound, KeyError):
            logger.error("worker.missing_s3_object", object_key=object_key)
            return await self._handle_failure(job, tenant_id, "Missing S3 object")

        # 5. Parse document
        # Resolve mime from filename extension or document metadata
        mime = "text/markdown"
        if object_key.endswith(".pdf"):
            mime = "application/pdf"
        elif object_key.endswith(".html"):
            mime = "text/html"
        elif object_key.endswith(".csv"):
            mime = "text/csv"

        parser = self.parsers.get(mime)
        if not parser:
            logger.error("worker.no_parser_for_mime", mime=mime)
            return await self._handle_failure(job, tenant_id, f"No parser for {mime}")

        try:
            filename = object_key.rsplit("/", 1)[-1]
            parsed_doc = await parser.parse(content, mime=mime, filename=filename)
        except Exception as exc:
            logger.error("worker.parse_failed", error=str(exc))
            return await self._handle_failure(job, tenant_id, f"Parse error: {exc}")

        # 6. Chunk document (CPU-bound)
        try:
            drafts = await run_cpu_bound(self.chunker.chunk, parsed_doc, title=parsed_doc.title)
        except Exception as exc:
            logger.error("worker.chunk_failed", error=str(exc))
            return await self._handle_failure(job, tenant_id, f"Chunking error: {exc}")

        # 7. Generate dense embeddings
        try:
            embed_texts = [d.embed_text for d in drafts]
            embeddings = await self.embedder.embed_documents(embed_texts)
        except Exception as exc:
            logger.error("worker.embedding_failed", error=str(exc))
            return await self._handle_failure(job, tenant_id, f"Embedding error: {exc}")

        # 8. Transactionally replace chunks & complete job
        doc_id = document_id or job.document_id
        chunk_models = []
        for idx, (draft, vector) in enumerate(zip(drafts, embeddings, strict=True)):
            chunk_models.append(SimpleNamespace(
                id=str(uuid4()),
                tenant_id=tenant_id,
                document_id=doc_id,
                chunk_index=idx,
                text=draft.text,
                embed_text=draft.embed_text,
                heading_path=list(draft.heading_path) if draft.heading_path else [],
                page_number=draft.page,
                token_count=draft.token_count,
                embedding=vector,
            ))

        try:
            async with self.documents.transaction():
                await self.documents.replace_chunks(doc_id, chunk_models, tenant_id=tenant_id)
                job.transition_to(JobStatus.COMPLETED)
                await self.documents.save_job(job, tenant_id=tenant_id)
        except Exception as exc:
            logger.error("worker.persist_failed", error=str(exc))
            return await self._handle_failure(job, tenant_id, f"Persist error: {exc}")

        logger.info("worker.job_completed", job_id=job_id, chunks_count=len(chunk_models))
        return IngestOutcome.COMPLETED

    async def _handle_failure(self, job: Any, tenant_id: str, reason: str) -> IngestOutcome:
        if job.attempts >= self.max_retries:
            job.transition_to(JobStatus.FAILED)
            job.error_message = reason
            await self.documents.save_job(job, tenant_id=tenant_id)
            return IngestOutcome.DEAD_LETTERED
        else:
            job.transition_to(JobStatus.QUEUED)
            await self.documents.save_job(job, tenant_id=tenant_id)
            return IngestOutcome.RETRY
```

### 8.2 Ingestion Worker Daemon Loop (`src/ragassist/worker/main.py`)

```python
# src/ragassist/worker/main.py
import asyncio
from typing import Any, Callable
import structlog

from ragassist.modules.knowledge.application.process_job import IngestOutcome
from ragassist.platform.queue.ports import MessageQueue

logger = structlog.get_logger(__name__)

class IngestionWorker:
    """Async background worker daemon polling SQS and dispatching ingestion jobs."""

    def __init__(
        self,
        queue: MessageQueue,
        handler: Callable[[str], Any],
        concurrency: int = 4,
        poll_wait_seconds: int = 10,
    ) -> None:
        self.queue = queue
        self.handler = handler
        self.concurrency = concurrency
        self.poll_wait_seconds = poll_wait_seconds
        self._semaphore = asyncio.Semaphore(concurrency)
        self._in_flight: set[asyncio.Task[None]] = set()

    async def run_until_stopped(self, stop: asyncio.Event) -> None:
        logger.info("worker.started", concurrency=self.concurrency, poll_wait=self.poll_wait_seconds)

        while not stop.is_set():
            try:
                # Receive messages up to available semaphore capacity
                messages = await self.queue.receive(
                    max_messages=min(10, self.concurrency),
                    wait_time_seconds=self.poll_wait_seconds if not stop.is_set() else 0,
                )
                if not messages:
                    if stop.is_set():
                        break
                    await asyncio.sleep(0.1)
                    continue

                for msg in messages:
                    task = asyncio.create_task(self._process_message(msg))
                    self._in_flight.add(task)
                    task.add_done_callback(self._in_flight.discard)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("worker.loop_error", error=str(exc))
                await asyncio.sleep(1.0)

        # Graceful shutdown: wait for all in-flight tasks to finish
        if self._in_flight:
            logger.info("worker.draining_in_flight", count=len(self._in_flight))
            await asyncio.gather(*list(self._in_flight), return_exceptions=True)
        logger.info("worker.stopped")

    async def _process_message(self, msg: Any) -> None:
        async with self._semaphore:
            receipt = getattr(msg, "receipt", getattr(msg, "receipt_handle", None))
            body = getattr(msg, "body", "")
            try:
                outcome = await self.handler(body)
                # On success, duplicate skip, malformed rejection, or terminal dead-lettering, delete from SQS
                if outcome in (
                    IngestOutcome.COMPLETED,
                    IngestOutcome.DUPLICATE_SKIPPED,
                    IngestOutcome.REJECTED,
                    IngestOutcome.DEAD_LETTERED,
                ):
                    if receipt:
                        await self.queue.delete(receipt)
                # On RETRY: do not delete; let SQS visibility timeout expire for redelivery
            except Exception as exc:
                logger.error("worker.handler_unhandled_exception", error=str(exc), message_id=getattr(msg, "message_id", None))
```

---

## 9. Knowledge Upload REST Router (`src/ragassist/modules/knowledge/api/router.py`)

```python
# src/ragassist/modules/knowledge/api/router.py
import json
import pathlib
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
import structlog

from ragassist.modules.knowledge.domain.models import FileTooLarge, UnsupportedMimeType
from ragassist.platform.queue.ports import MessageQueue
from ragassist.platform.storage.ports import ObjectStore
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.db.models import DocumentModel
from ragassist.shared.db.uow import tenant_uow
from ragassist.shared.domain import TenantId
from ragassist.shared.security.deps import get_current_principal
from ragassist.shared.security.jwt import Principal

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/knowledge", tags=["Knowledge"])

ALLOWED_MIMES = frozenset({
    "application/pdf",
    "text/html",
    "text/markdown",
    "text/csv",
})
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MiB

class UploadResponse(BaseModel):
    job_id: str
    document_id: str
    title: str
    status: str
    object_key: str

@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload document for ingestion",
)
async def upload_document(
    file: UploadFile = File(...),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> UploadResponse:
    tenant_id_str = str(principal.tenant_id)
    user_id_str = str(principal.user_id)

    # 1. MIME Validation
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported media type: {content_type}. Allowed: {sorted(ALLOWED_MIMES)}",
        )

    # 2. Read content & Size Validation
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_BYTES} bytes",
        )

    # 3. Path Traversal Protection
    clean_filename = pathlib.Path(file.filename or "uploaded.bin").name.replace("..", "_")
    document_id = uuid4()
    job_id = uuid4()
    object_key = f"tenants/{tenant_id_str}/documents/{document_id}/{clean_filename}"

    # Lazily resolve storage and queue adapters
    from ragassist.platform.storage.s3 import S3ObjectStore
    from ragassist.platform.queue.sqs import SQSMessageQueue

    store = S3ObjectStore(settings)
    queue = SQSMessageQueue(settings=settings)

    # 4. S3 Put
    s3_uri = await store.put(object_key, content, content_type=content_type)

    try:
        # 5. Database transaction with RLS
        async with tenant_uow(TenantId(principal.tenant_id)) as uow:
            doc = DocumentModel(
                id=document_id,
                tenant_id=principal.tenant_id,
                title=clean_filename,
                s3_uri=s3_uri,
                mime=content_type,
                status="queued",
            )
            uow.session.add(doc)
            # IngestionJob record is created via repository or session
            await uow.commit()

        # 6. SQS Enqueue
        message_body = {
            "job_id": str(job_id),
            "document_id": str(document_id),
            "tenant_id": tenant_id_str,
            "object_key": object_key,
        }
        await queue.send(message_body)

        return UploadResponse(
            job_id=str(job_id),
            document_id=str(document_id),
            title=clean_filename,
            status="queued",
            object_key=object_key,
        )

    except Exception as exc:
        logger.error("upload.failed_rolling_back", error=str(exc))
        await store.delete(object_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue document ingestion",
        ) from exc
```

---

## 10. Comprehensive Test Matrix & Validation Strategy

| Test File | Test Suite / Class | Scope | Key Invariants Verified |
|-----------|--------------------|-------|--------------------------|
| `tests/unit/platform/storage/test_s3_storage.py` | `TestS3ObjectStore` | Unit (mocked `aioboto3`) | Verify `put`, `get`, `exists`, `delete`, `upload_stream`, presigned URL, and `ObjectNotFound` error handling. |
| `tests/unit/platform/queue/test_sqs_queue.py` | `TestSQSMessageQueue` | Unit (mocked `aioboto3`) | Verify `send`, `receive`, `delete`, `change_visibility`, `receive_count`, and URL resolution. |
| `tests/unit/modules/knowledge/test_job_state.py` | `TestJobStateTransitions` | Unit | State machine: only valid transitions permitted (`queued -> running -> completed | failed | queued`). |
| `tests/unit/modules/knowledge/test_upload_use_case.py` | `TestUploadDocument` | Unit (Fakes) | Storage prefix `tenants/{tenant_id}/`, SQS body contract, MIME/size validation, traversal protection, atomicity rollback on SQS failure. |
| `tests/unit/modules/knowledge/test_ingestion_worker.py` | `TestProcessIngestionJob` & `TestIngestionWorkerLoop` | Unit (Fakes) | Idempotent duplicate skips, tenant matching defense, retry budget, DLQ transition, graceful worker loop termination. |
| `tests/integration/test_rls_and_uow.py` | `TestRowLevelSecurityMatrix` & `TestRoleHardening` | Integration (Postgres container) | Verifies RLS across all tables (`tenants`, `users`, `documents`, `document_chunks`, `ingestion_jobs`); resolves DEFECT-09 and DEFECT-10. |
| `tests/integration/test_retrieval_postgres.py` | `TestVectorRetrieval` & `TestKeywordRetrieval` | Integration (pgvector container) | HNSW vector cosine distance search, `relaxed_order` scan, GIN FTS tsvector matching, cross-tenant isolation. |
| `tests/integration/test_localstack_init.py` | `TestInitScript` | Integration (LocalStack) | Verifies `ragassist-docs` bucket, `ragassist-ingest` queue with redrive policy (`maxReceiveCount: 3`) to `ragassist-ingest-dlq`. |

---

## 11. Implementation Action Plan for Milestone 2 Workers

1. **Fix `UnitOfWork` (DEFECT-10)**: Update `src/ragassist/shared/db/uow.py` to check `if not self.session.in_transaction(): await self.session.begin()`.
2. **Implement Platform Storage**:
   - Write `src/ragassist/platform/storage/ports.py` (with `ObjectNotFound`).
   - Write `src/ragassist/platform/storage/s3.py` (with `S3ObjectStore` and `InMemoryObjectStore`).
3. **Implement Platform Queue**:
   - Write `src/ragassist/platform/queue/ports.py` (with `Received` DTO).
   - Write `src/ragassist/platform/queue/sqs.py` (with `SQSMessageQueue` and `InMemoryMessageQueue`).
4. **Implement Persistence Models & Repository**:
   - Write `src/ragassist/modules/knowledge/adapters/persistence/models.py` (`DocumentModel`, `ChunkModel`, `IngestionJobModel`).
   - Write `src/ragassist/modules/knowledge/adapters/persistence/repository.py` (`PostgresDocumentRepository`).
5. **Implement RLS Policies (DEFECT-09)**:
   - Update `infra/postgres/init.sql` with `FORCE ROW LEVEL SECURITY` and `CREATE POLICY` statements.
   - Update `tests/integration/test_rls_and_uow.py` to include `"documents"`, `"document_chunks"`, `"ingestion_jobs"` in `COVERED_TABLES`.
6. **Implement Alembic Migration**:
   - Add `0001_initial_knowledge_and_rls.py` creating tables, vector extension, HNSW index, GIN index, and RLS policies.
7. **Implement Knowledge Domain & Application**:
   - Write `src/ragassist/modules/knowledge/domain/models.py` (`IngestionJob`, `JobStatus`, `InvalidTransition`, `UnsupportedMimeType`, `FileTooLarge`).
   - Write `src/ragassist/modules/knowledge/application/upload.py` (`UploadDocument`, `UploadCommand`, `UploadResult`).
   - Write `src/ragassist/modules/knowledge/application/process_job.py` (`ProcessIngestionJob`, `IngestOutcome`).
8. **Implement Ingestion Worker Daemon**:
   - Write `src/ragassist/worker/main.py` (`IngestionWorker`).
   - Write `src/ragassist/worker/ingestion_worker.py` (entry point / daemon runner).
9. **Implement Upload REST Router**:
   - Write `src/ragassist/modules/knowledge/api/router.py` and register on FastAPI app in `src/ragassist/main.py`.
10. **Re-populate Test Fakes**:
    - Ensure `tests/fakes/object_store.py` and `tests/fakes/message_queue.py` are restored.
