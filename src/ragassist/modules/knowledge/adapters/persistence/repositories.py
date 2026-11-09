"""PostgreSQL repositories for the knowledge module: the API-facing store and the worker-facing repository.

Goal: persist documents, ingestion jobs and chunks (with pgvector embeddings) under row-level security.

Two classes, because the two callers speak different contracts (the existing in-memory store and the test fake
fix those contracts):

* ``PostgresKnowledgeStore`` serves the HTTP router and the ``UploadDocument`` use case: ``transaction()``,
  ``add_job``, ``add_document``, tenant-first lookups, listing and deletion.
* ``PostgresIngestionRepository`` serves ``ProcessIngestionJob``: ``get_job(job_id)``, an atomic ``claim_job``,
  ``save_job``, ``get_document`` and ``replace_chunks``. The queue message names the tenant; the worker binds that
  tenant for the duration of the message (``bind_tenant``), so a forged tenant simply finds no rows.

Decisions (docs consulted: PostgreSQL row security, pgvector README "Inserting vectors" / casting a text literal, SQL
``to_tsvector``/``websearch_to_tsquery``, SQS visibility timeout semantics):

* A claim is one conditional ``UPDATE ... WHERE status = 'queued'`` (or a claim older than the visibility window, so a
  crashed worker's job is picked up again instead of staying ``parsing`` forever).
* Chunks inherit the tenant of their document, never of the message, so a chunk can not outlive its owner's scope;
  global documents (tenant NULL) are written only through the owner role (the seed command), never by ``app_user``.
* Chunk replacement is one transaction: delete the old chunks, insert the new ones, so a failed swap keeps the old set.
"""

from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from ragassist.modules.knowledge.domain import IngestionJob, JobStatus
from ragassist.shared.db.scoped import ScopedDatabase

QUEUED, PROCESSING, COMPLETED, FAILED = "queued", "processing", "completed", "failed"


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else datetime.now(timezone.utc).isoformat()


def _status(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw) if raw is not None else QUEUED


def _document_status(job_status: str) -> str:
    """Map a job status to the status the document shows."""
    return {"completed": COMPLETED, "failed": FAILED, "queued": QUEUED}.get(job_status, PROCESSING)


def _as_uuid(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


def _vector_literal(vector: Any) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


class PostgresKnowledgeStore:
    """Router- and upload-facing persistence (tenant-first lookups, atomic upload transaction)."""

    def __init__(self, database: ScopedDatabase) -> None:
        self._db = database

    # -- upload use case contract ------------------------------------------------------------------
    def transaction(self) -> AbstractAsyncContextManager[None]:
        return self._db.transaction()

    async def defer_until_commit(self, callback: Any) -> None:
        await self._db.defer_until_commit(callback)

    async def add_job(self, job: IngestionJob | dict[str, Any]) -> None:
        if isinstance(job, dict):
            job_id, document_id, tenant_id = job["job_id"], job["document_id"], job["tenant_id"]
            status, attempts = _status(job.get("status")), int(job.get("attempts", 0))
        else:
            job_id, document_id, tenant_id = job.job_id, job.document_id, job.tenant_id
            status, attempts = _status(job.status), int(job.attempts)
        async with self._db.scope(tenant_id) as session:
            await session.execute(
                text(
                    "INSERT INTO ingestion_jobs (id, tenant_id, document_id, status, attempts) "
                    "VALUES (:id, :tenant_id, :document_id, :status, :attempts) ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": _as_uuid(job_id),
                    "tenant_id": _as_uuid(tenant_id),
                    "document_id": _as_uuid(document_id),
                    "status": status,
                    "attempts": attempts,
                },
            )

    async def add_document(self, doc: Any) -> None:
        """Insert a document row; a second call for the same id (the router's follow-up) changes nothing."""
        if isinstance(doc, dict):
            doc_id = doc.get("document_id") or doc.get("id")
            tenant_id = doc.get("tenant_id") or None
            filename = doc.get("filename") or "document"
            content_type = doc.get("content_type") or "application/octet-stream"
            size = int(doc.get("file_size_bytes") or 0)
            object_key = doc.get("object_key") or doc.get("s3_key") or ""
            content_hash = doc.get("content_hash") or ""
        else:
            doc_id = getattr(doc, "id", None) or getattr(doc, "document_id", None)
            tenant_id = getattr(doc, "tenant_id", None) or None
            filename = getattr(doc, "filename", "document")
            content_type = getattr(doc, "content_type", "application/octet-stream")
            size = int(getattr(doc, "file_size_bytes", 0))
            object_key = getattr(doc, "s3_key", "") or getattr(doc, "object_key", "")
            content_hash = getattr(doc, "content_hash", "")
        async with self._db.scope(tenant_id) as session:
            await session.execute(
                text(
                    "INSERT INTO documents (id, tenant_id, title, filename, content_type, file_size_bytes, "
                    "object_key, content_hash, status) VALUES (:id, :tenant_id, :title, :filename, :content_type, "
                    ":size, :object_key, :content_hash, 'queued') ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": _as_uuid(doc_id),
                    "tenant_id": _as_uuid(tenant_id),
                    "title": filename,
                    "filename": filename,
                    "content_type": content_type,
                    "size": size,
                    "object_key": object_key,
                    "content_hash": content_hash,
                },
            )

    # -- router contract ---------------------------------------------------------------------------
    @staticmethod
    def _document_dict(row: Any) -> dict[str, Any]:
        return {
            "document_id": str(row.id),
            "tenant_id": str(row.tenant_id) if row.tenant_id else "",
            "filename": row.filename,
            "content_type": row.content_type,
            "file_size_bytes": int(row.file_size_bytes),
            "status": row.status,
            "object_key": row.object_key,
            "error_message": row.error_message,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    async def get_document(self, tenant_id: Any, document_id: str) -> dict[str, Any] | None:
        doc_id = self._uuid_or_none(document_id)
        if doc_id is None:
            return None
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text("SELECT * FROM documents WHERE id = :id AND tenant_id = :tenant_id"),
                    {"id": doc_id, "tenant_id": _as_uuid(tenant_id)},
                )
            ).first()
        return self._document_dict(row) if row else None

    async def list_documents(self, tenant_id: Any, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        params = {"tenant_id": _as_uuid(tenant_id), "limit": limit, "offset": offset}
        async with self._db.scope(tenant_id) as session:
            total = (
                await session.execute(text("SELECT count(*) FROM documents WHERE tenant_id = :tenant_id"), params)
            ).scalar_one()
            rows = (
                await session.execute(
                    text(
                        "SELECT * FROM documents WHERE tenant_id = :tenant_id "
                        "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                    ),
                    params,
                )
            ).all()
        return [self._document_dict(r) for r in rows], int(total)

    async def delete_document(self, tenant_id: Any, document_id: str) -> bool:
        doc_id = self._uuid_or_none(document_id)
        if doc_id is None:
            return False
        async with self._db.scope(tenant_id) as session:
            result = await session.execute(
                text("DELETE FROM documents WHERE id = :id AND tenant_id = :tenant_id"),
                {"id": doc_id, "tenant_id": _as_uuid(tenant_id)},
            )
        return bool(result.rowcount)

    async def get_job(self, tenant_id: Any, job_id: str) -> dict[str, Any] | None:
        job_uuid = self._uuid_or_none(job_id)
        if job_uuid is None:
            return None
        async with self._db.scope(tenant_id) as session:
            row = (
                await session.execute(
                    text("SELECT * FROM ingestion_jobs WHERE id = :id AND tenant_id = :tenant_id"),
                    {"id": job_uuid, "tenant_id": _as_uuid(tenant_id)},
                )
            ).first()
        if row is None:
            return None
        return {
            "job_id": str(row.id),
            "document_id": str(row.document_id),
            "tenant_id": str(row.tenant_id),
            "status": row.status,
            "attempts": int(row.attempts),
            "chunks_created": int(row.chunks_created),
            "tokens_indexed": int(row.tokens_indexed),
            "error_message": row.error_message,
            "created_at": _iso(row.created_at),
        }

    @staticmethod
    def _uuid_or_none(value: Any) -> UUID | None:
        try:
            return _as_uuid(value)
        except (ValueError, AttributeError, TypeError):
            return None


class PostgresIngestionRepository:
    """Worker-facing persistence for ``ProcessIngestionJob``."""

    def __init__(self, database: ScopedDatabase, *, claim_timeout_seconds: int = 240) -> None:
        self._db = database
        self._claim_timeout = claim_timeout_seconds
        self._tenant: ContextVar[str | None] = ContextVar("ingestion_repository_tenant", default=None)

    def bind_tenant(self, tenant_id: Any) -> Token[str | None]:
        """Bind the tenant named by the queue message for the duration of its handling."""
        return self._tenant.set(str(tenant_id) if tenant_id else None)

    def unbind_tenant(self, token: Token[str | None]) -> None:
        self._tenant.reset(token)

    async def get_job(self, job_id: str) -> IngestionJob | None:
        job_uuid = PostgresKnowledgeStore._uuid_or_none(job_id)
        if job_uuid is None:
            return None
        async with self._db.scope(self._tenant.get()) as session:
            row = (
                await session.execute(text("SELECT * FROM ingestion_jobs WHERE id = :id"), {"id": job_uuid})
            ).first()
        if row is None:
            return None
        return IngestionJob(
            id=row.id,
            created_at=row.created_at,
            document_id=str(row.document_id),
            tenant_id=str(row.tenant_id),
            status=JobStatus(row.status) if row.status in JobStatus._value2member_map_ else row.status,
            attempts=int(row.attempts),
            chunks_created=int(row.chunks_created),
            tokens_indexed=int(row.tokens_indexed),
            error_message=row.error_message,
        )

    async def claim_job(self, job_id: str, *, tenant_id: Any) -> bool:
        """Atomically move a queued job (or a stale claim) to ``parsing`` and count the attempt."""
        async with self._db.scope(tenant_id) as session:
            claimed = (
                await session.execute(
                    text(
                        "UPDATE ingestion_jobs SET status = 'parsing', attempts = attempts + 1, started_at = now(), "
                        "updated_at = now() WHERE id = :id AND tenant_id = :tenant_id AND ("
                        "status = 'queued' OR (status NOT IN ('completed', 'failed') "
                        "AND updated_at < now() - make_interval(secs => :stale))) RETURNING document_id"
                    ),
                    {"id": _as_uuid(job_id), "tenant_id": _as_uuid(tenant_id), "stale": self._claim_timeout},
                )
            ).first()
            if claimed is None:
                return False
            await session.execute(
                text("UPDATE documents SET status = 'processing', updated_at = now() WHERE id = :id"),
                {"id": claimed.document_id},
            )
        return True

    async def get_attempts(self, job_id: str) -> int:
        async with self._db.scope(self._tenant.get()) as session:
            value = (
                await session.execute(
                    text("SELECT attempts FROM ingestion_jobs WHERE id = :id"), {"id": _as_uuid(job_id)}
                )
            ).scalar_one_or_none()
        return int(value or 0)

    async def get_document(self, document_id: str) -> SimpleNamespace | None:
        async with self._db.scope(self._tenant.get()) as session:
            row = (
                await session.execute(text("SELECT * FROM documents WHERE id = :id"), {"id": _as_uuid(document_id)})
            ).first()
        if row is None:
            return None
        return SimpleNamespace(
            id=row.id,
            tenant_id=row.tenant_id,
            title=row.title,
            filename=row.filename,
            content_type=row.content_type,
            mime=row.content_type,
            s3_key=row.object_key,
            object_key=row.object_key,
        )

    async def save_job(self, job: IngestionJob, *, tenant_id: Any) -> None:
        status = _status(job.status)
        async with self._db.scope(tenant_id) as session:
            counts = (
                await session.execute(
                    text(
                        "SELECT count(*) AS n, coalesce(sum(token_count), 0) AS tokens FROM chunks "
                        "WHERE document_id = :doc"
                    ),
                    {"doc": _as_uuid(job.document_id)},
                )
            ).one()
            await session.execute(
                text(
                    "UPDATE ingestion_jobs SET status = CAST(:status AS varchar), error_message = :error, "
                    "chunks_created = :chunks, tokens_indexed = :tokens, updated_at = now(), "
                    "completed_at = CASE WHEN CAST(:status AS varchar) = 'completed' THEN now() ELSE completed_at END "
                    "WHERE id = :id AND tenant_id = :tenant_id"
                ),
                {
                    "status": status,
                    "error": job.error_message,
                    "chunks": int(counts.n) if status == COMPLETED else 0,
                    "tokens": int(counts.tokens) if status == COMPLETED else 0,
                    "id": _as_uuid(job.job_id),
                    "tenant_id": _as_uuid(tenant_id),
                },
            )
            await session.execute(
                text("UPDATE documents SET status = :status, error_message = :error, updated_at = now() WHERE id = :id"),
                {"status": _document_status(status), "error": job.error_message, "id": _as_uuid(job.document_id)},
            )

    async def replace_chunks(self, document_id: str, chunks: list[Any], *, tenant_id: Any) -> None:
        """Swap the document's chunks in one transaction; a failure keeps the previous set."""
        doc_uuid = _as_uuid(document_id)
        async with self._db.scope(tenant_id) as session:
            owner = (
                await session.execute(text("SELECT tenant_id, title FROM documents WHERE id = :id"), {"id": doc_uuid})
            ).first()
            if owner is None:
                raise LookupError(f"document {document_id} is not visible to this tenant")
            await session.execute(text("DELETE FROM chunks WHERE document_id = :id"), {"id": doc_uuid})
            if not chunks:
                return
            rows = [
                {
                    "id": str(chunk.id),
                    "tenant_id": owner.tenant_id,
                    "document_id": doc_uuid,
                    "text": chunk.text,
                    "embed_text": getattr(chunk, "embed_text", None) or chunk.text,
                    "heading_path": json.dumps(list(getattr(chunk, "heading_path", ()) or ())),
                    "page": getattr(chunk, "page", None),
                    "title": (owner.title or "")[:255],
                    "embedding": _vector_literal(chunk.embedding),
                    "chunk_index": getattr(chunk, "chunk_index", None),
                    "token_count": int(getattr(chunk, "token_count", 0) or 0),
                }
                for chunk in chunks
            ]
            await session.execute(
                text(
                    "INSERT INTO chunks (id, tenant_id, document_id, text, embed_text, heading_path, page, title, "
                    "embedding, fts, chunk_index, token_count) VALUES (:id, :tenant_id, :document_id, :text, "
                    ":embed_text, CAST(:heading_path AS jsonb), :page, :title, CAST(:embedding AS vector), "
                    "to_tsvector('english', :text), :chunk_index, :token_count)"
                ),
                rows,
            )


def new_chunk_id() -> str:
    return str(uuid4())
