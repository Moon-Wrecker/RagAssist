"""Application service for document ingestion and asynchronous job processing (ADR 0003).

Goal: Orchestrate atomic document uploads, validation, idempotent SQS message processing,
parsing, 5-pass chunking, dense embedding, and atomic chunk swaps under tenant isolation.

Consulted documentation & references:
- ADR 0001: PostgreSQL + pgvector unified storage & atomic transaction guarantees
- ADR 0003: 5-Pass structure-aware hybrid chunking
- AWS SQS standard idempotency & visibility timeout redrive best practices
- Hexagonal architecture: application service dependent only on domain entities and abstract ports
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from types import SimpleNamespace
from typing import Any, Mapping
from uuid import UUID, uuid4

import structlog

from ragassist.modules.knowledge.domain import (
    Document,
    FileTooLarge,
    IngestionJob,
    JobStatus,
    Parser,
    UnsupportedMimeType,
)


logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class UploadCommand:
    """Command carrying raw document upload payload."""

    tenant_id: str
    user_id: str
    filename: str
    mime: str
    content: bytes


@dataclass(frozen=True)
class UploadResult:
    """Result of a successful upload operation."""

    job_id: str
    document_id: str
    object_key: str


class UploadDocument:
    """Application use case for validating and uploading documents atomically."""

    def __init__(
        self,
        store: Any,
        queue: Any,
        documents: Any,
        max_bytes: int = 10 * 1024 * 1024,
        allowed_mimes: Any = None,
    ) -> None:
        self.store = store
        self.queue = queue
        self.documents = documents
        self.max_bytes = max_bytes
        self.allowed_mimes = (
            allowed_mimes
            if allowed_mimes is not None
            else frozenset(
                {
                    "text/markdown",
                    "text/html",
                    "text/csv",
                    "application/pdf",
                }
            )
        )

    async def execute(self, command: UploadCommand) -> UploadResult:
        if command.mime not in self.allowed_mimes:
            raise UnsupportedMimeType(f"MIME type '{command.mime}' is not supported")

        if len(command.content) > self.max_bytes:
            raise FileTooLarge(
                f"File size {len(command.content)} bytes exceeds limit {self.max_bytes}"
            )

        # Sanitize filename against directory traversal
        # Split on both separators: a Windows-style path must not survive on a POSIX host.
        safe_filename = re.split(r"[\\/]", command.filename)[-1].replace("\x00", "")
        while ".." in safe_filename:
            safe_filename = safe_filename.replace("..", "")
        if not safe_filename or set(safe_filename) <= {".", "_"}:
            safe_filename = "document"

        document_id = str(uuid4())
        job_id = str(uuid4())
        object_key = f"tenants/{command.tenant_id}/documents/{document_id}/{safe_filename}"

        job = IngestionJob(
            job_id=job_id,
            document_id=document_id,
            tenant_id=command.tenant_id,
            status=JobStatus.QUEUED,
            attempts=0,
        )

        doc = Document(
            id=UUID(document_id),
            created_at=getattr(job, "created_at", None),
            tenant_id=command.tenant_id,
            filename=safe_filename,
            content_type=command.mime,
            file_size_bytes=len(command.content),
            s3_key=object_key,
            content_hash=hashlib.sha256(command.content).hexdigest(),
        )

        message_body = json.dumps(
            {
                "job_id": job_id,
                "tenant_id": command.tenant_id,
                "object_key": object_key,
                "document_id": document_id,
            }
        )

        # Write inside repository transaction so failed queue or storage rolls back state
        async with self.documents.transaction():
            object_written = False
            try:
                # 1. Store bytes
                if hasattr(self.store, "put_object"):
                    await self.store.put_object(object_key, command.content, content_type=command.mime)
                elif hasattr(self.store, "put"):
                    await self.store.put(object_key, command.content)
                else:
                    raise AttributeError("Store has neither put_object nor put method")
                object_written = True

                # 2. Add job and document rows
                await self.documents.add_job(job)
                await self.documents.add_document(doc)

                # 3. Enqueue SQS message
                if hasattr(self.queue, "send"):
                    await self.queue.send(message_body)
                elif hasattr(self.queue, "send_message"):
                    from ragassist.shared.config.settings import get_settings

                    await self.queue.send_message(
                        queue_name=get_settings().SQS_QUEUE_INGEST,
                        message_body=json.loads(message_body),
                    )
            except Exception:
                if object_written:
                    try:
                        if hasattr(self.store, "delete_object"):
                            await self.store.delete_object(object_key)
                        elif hasattr(self.store, "delete"):
                            await self.store.delete(object_key)
                    except Exception as cleanup_exc:  # noqa: BLE001 - the original error is re-raised below
                        logger.warning(
                            "ingestion.orphan_object", object_key=object_key, error=str(cleanup_exc)
                        )
                raise

        return UploadResult(job_id=job_id, document_id=document_id, object_key=object_key)


class IngestOutcome(str, Enum):
    """Outcome status of processing an ingestion message."""

    COMPLETED = "COMPLETED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    RETRY = "RETRY"
    DEAD_LETTERED = "DEAD_LETTERED"
    REJECTED = "REJECTED"


class ProcessIngestionJob:
    """Use case processing asynchronous document ingestion jobs from the queue."""

    def __init__(
        self,
        documents: Any,
        store: Any,
        parsers: Mapping[str, Parser],
        chunker: Any,
        embedder: Any,
        max_retries: int = 3,
    ) -> None:
        self.documents = documents
        self.store = store
        self.parsers = parsers
        self.chunker = chunker
        self.embedder = embedder
        self.max_retries = max_retries

    async def handle(self, body: str | dict[str, Any]) -> IngestOutcome:
        # Validate body payload
        if isinstance(body, str):
            try:
                payload = json.loads(body)
            except Exception:
                return IngestOutcome.REJECTED
        elif isinstance(body, dict):
            payload = body
        else:
            return IngestOutcome.REJECTED

        if not isinstance(payload, dict):
            return IngestOutcome.REJECTED

        job_id = payload.get("job_id")
        tenant_id = payload.get("tenant_id")
        object_key = payload.get("object_key")

        if not job_id or not tenant_id:
            return IngestOutcome.REJECTED

        # Look up job in document repository
        try:
            job = await self.documents.get_job(job_id)
        except Exception:
            return IngestOutcome.REJECTED

        if job is None:
            return IngestOutcome.REJECTED

        # Defense-in-depth: Tenant in message must strictly match job row
        if str(job.tenant_id) != str(tenant_id):
            return IngestOutcome.REJECTED

        # Idempotency check: Already completed jobs are skipped
        if job.status == "completed" or job.status == JobStatus.COMPLETED:
            return IngestOutcome.DUPLICATE_SKIPPED

        # Claim the job atomically (queued -> running)
        claimed = await self.documents.claim_job(job_id, tenant_id=tenant_id)
        if not claimed:
            return IngestOutcome.DUPLICATE_SKIPPED

        def _with_status(j: Any, status: str, error: str | None = None) -> Any:
            try:
                return replace(j, status=status, error_message=error)
            except Exception:
                try:
                    j.status = status
                    j.error_message = error
                    return j
                except Exception:
                    return j

        async def _handle_failure(stage: str, exc: BaseException | None = None) -> IngestOutcome:
            # The job row is returned by the API, so it carries the stage and exception class only; the
            # exception text (hosts, SQL, file contents) goes to the log.
            reason = f"{stage} failed ({type(exc).__name__})" if exc is not None else f"{stage} failed"
            logger.warning(
                "ingestion.step_failed",
                job_id=job_id,
                stage=stage,
                error=str(exc) if exc is not None else stage,
            )
            current_attempts = getattr(job, "attempts", 0)
            if hasattr(self.documents, "attempts_for"):
                current_attempts = max(current_attempts, self.documents.attempts_for(job_id))
            elif hasattr(self.documents, "get_attempts"):
                current_attempts = max(current_attempts, await self.documents.get_attempts(job_id))
            else:
                current_attempts = current_attempts + 1

            if current_attempts >= self.max_retries:
                updated = _with_status(job, "failed", reason)
                await self.documents.save_job(updated, tenant_id=tenant_id)
                return IngestOutcome.DEAD_LETTERED
            else:
                updated = _with_status(job, "queued", reason)
                await self.documents.save_job(updated, tenant_id=tenant_id)
                return IngestOutcome.RETRY

        # Retrieve document record and object bytes
        try:
            doc = await self.documents.get_document(job.document_id)
        except Exception as exc:
            return await _handle_failure("load document", exc)

        # The key comes from the document row, never from the queue message: a message can be forged by anything
        # that can write to the queue, the row cannot. It must also live under this tenant's prefix.
        key = getattr(doc, "object_key", None) or getattr(doc, "s3_key", None) or object_key
        if not key:
            return await _handle_failure("document has no object key")
        if not str(key).startswith(f"tenants/{tenant_id}/"):
            return await _handle_failure("object key outside the tenant")

        try:
            if hasattr(self.store, "get_object"):
                content = await self.store.get_object(key)
            elif hasattr(self.store, "get"):
                content = await self.store.get(key)
            else:
                content = None
        except Exception as exc:
            return await _handle_failure("read object", exc)

        # Parse document
        mime = getattr(doc, "mime", getattr(doc, "content_type", "text/markdown"))
        parser = self.parsers.get(mime)
        if not parser:
            for p in self.parsers.values():
                if p.supports(mime):
                    parser = p
                    break
        if not parser:
            return await _handle_failure(f"no parser for {mime}")

        try:
            filename = getattr(doc, "title", getattr(doc, "filename", "document"))
            parsed = await parser.parse(content, mime=mime, filename=filename)
        except Exception as exc:
            return await _handle_failure("parse", exc)

        # Chunk document
        try:
            title = getattr(doc, "title", getattr(parsed, "title", "Document"))
            chunks = self.chunker.chunk(parsed, title=title)
        except Exception as exc:
            return await _handle_failure("chunk", exc)

        # Generate dense embeddings
        try:
            embed_texts = [
                getattr(c, "embed_text", getattr(c, "clean_text", getattr(c, "text", "")))
                for c in chunks
            ]
            vectors = await self.embedder.embed_documents(embed_texts)
        except Exception as exc:
            return await _handle_failure("embed", exc)

        # Atomic chunk swap
        try:
            chunk_records = []
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                chunk_records.append(
                    SimpleNamespace(
                        id=uuid4(),
                        document_id=job.document_id,
                        tenant_id=tenant_id,
                        text=getattr(chunk, "text", getattr(chunk, "content", "")),
                        embed_text=getattr(chunk, "embed_text", getattr(chunk, "clean_text", "")),
                        heading_path=tuple(getattr(chunk, "heading_path", ())),
                        page=getattr(chunk, "page", getattr(chunk, "page_number", None)),
                        parent=getattr(chunk, "parent", None),
                        token_count=getattr(chunk, "token_count", 0),
                        embedding=vector,
                        chunk_index=i,
                    )
                )
            await self.documents.replace_chunks(
                job.document_id, chunk_records, tenant_id=tenant_id
            )
        except Exception as exc:
            return await _handle_failure("store chunks", exc)

        # Mark job completed
        updated = _with_status(job, "completed")
        await self.documents.save_job(updated, tenant_id=tenant_id)
        return IngestOutcome.COMPLETED
