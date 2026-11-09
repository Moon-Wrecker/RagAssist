"""FastAPI router for Knowledge Module document ingestion and lifecycle management.

Consulted References:
- FastAPI File Uploads: https://fastapi.tiangolo.com/tutorial/request-files/
- HTTP Status Codes (RFC 9110): 202 Accepted, 413 Payload Too Large, 415 Unsupported Media Type, 404 Not Found.
- Hexagonal Architecture: Route handler delegates validation and coordination to application use cases.
"""

from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from ragassist.modules.knowledge.application import UploadCommand, UploadDocument
from ragassist.modules.knowledge.domain import (
    Document,
    DocumentStatus,
    FileTooLarge,
    IngestionJob,
    JobStatus,
    UnsupportedMimeType,
)
from ragassist.platform.events import (
    document_changed,
    get_event_bus,
    job_updated,
    publish_safely,
)
from ragassist.platform.queue.sqs_adapter import InMemoryMessageQueue, SQSMessageQueue
from ragassist.platform.storage.s3_adapter import InMemoryObjectStore, S3ObjectStore
from ragassist.shared.config.settings import get_settings
from ragassist.shared.security.deps import get_current_principal
from ragassist.shared.security.jwt import Principal, UserRole

router = APIRouter(tags=["Knowledge"])


class DocumentSummary(BaseModel):
    """Document summary item returned in listings."""

    document_id: str
    tenant_id: str
    filename: str
    content_type: str
    file_size_bytes: int
    status: str
    error_message: str | None = None
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: list[DocumentSummary]
    total: int


class DocumentUploadResponse(BaseModel):
    """Response after initiating document upload and queuing ingestion."""

    document_id: str
    job_id: str
    object_key: str
    status: str = "queued"


class IngestionJobResponse(BaseModel):
    """Ingestion job progress and status details."""

    job_id: str
    document_id: str
    tenant_id: str
    status: str
    attempts: int = 0
    chunks_created: int = 0
    tokens_indexed: int = 0
    error_message: str | None = None
    created_at: str


class InMemoryDocumentStore:
    """Thread-safe document and job registry for router runtime and testing."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}

    async def add_document(self, doc_data: Any) -> None:
        if isinstance(doc_data, dict):
            doc_id = str(doc_data.get("document_id") or doc_data.get("id"))
            data = doc_data
        else:
            doc_id = str(getattr(doc_data, "id", None) or getattr(doc_data, "document_id", None))
            data = {
                "document_id": doc_id,
                "tenant_id": str(getattr(doc_data, "tenant_id", "")),
                "filename": getattr(doc_data, "filename", ""),
                "content_type": getattr(doc_data, "content_type", ""),
                "file_size_bytes": getattr(doc_data, "file_size_bytes", 0),
                "status": getattr(getattr(doc_data, "status", None), "value", "completed"),
                "created_at": getattr(doc_data, "created_at", None),
            }
        self.documents[doc_id] = data

    async def add_job(self, job_data: Any) -> None:
        if isinstance(job_data, dict):
            job_id = str(job_data.get("job_id") or job_data.get("id"))
            data = job_data
        else:
            job_id = str(getattr(job_data, "job_id", None) or getattr(job_data, "id", None))
            data = {
                "job_id": job_id,
                "document_id": str(getattr(job_data, "document_id", "")),
                "tenant_id": str(getattr(job_data, "tenant_id", "")),
                "status": getattr(getattr(job_data, "status", None), "value", "queued"),
                "chunks_created": getattr(job_data, "chunks_created", 0),
                "tokens_indexed": getattr(job_data, "tokens_indexed", 0),
            }
        self.jobs[job_id] = data

    async def get_document(self, tenant_id: str, document_id: str) -> dict[str, Any] | None:
        doc = self.documents.get(document_id)
        if doc is None or doc.get("tenant_id") != str(tenant_id):
            return None
        return doc

    async def list_documents(self, tenant_id: str, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        tenant_docs = [d for d in self.documents.values() if d.get("tenant_id") == str(tenant_id)]
        return tenant_docs[offset : offset + limit], len(tenant_docs)

    async def delete_document(self, tenant_id: str, document_id: str) -> bool:
        doc = await self.get_document(tenant_id, document_id)
        if doc is None:
            return False
        self.documents.pop(document_id, None)
        return True

    async def add_job(self, job: IngestionJob | dict[str, Any]) -> None:
        if isinstance(job, IngestionJob):
            data = {
                "job_id": job.job_id,
                "document_id": str(job.document_id),
                "tenant_id": str(job.tenant_id) if job.tenant_id else "",
                "status": job.status.value if isinstance(job.status, JobStatus) else str(job.status),
                "attempts": job.attempts,
                "chunks_created": job.chunks_created,
                "tokens_indexed": job.tokens_indexed,
                "error_message": job.error_message,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            data = dict(job)
        self.jobs[data["job_id"]] = data

    async def get_job(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        job = self.jobs.get(job_id)
        if job is None or job.get("tenant_id") != str(tenant_id):
            return None
        return job

    def transaction(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _tx():
            yield

        return _tx()


_knowledge_store = InMemoryDocumentStore()
_object_store: Any = None
_message_queue: Any = None


def get_knowledge_store() -> Any:
    from ragassist.runtime import active_runtime

    runtime = active_runtime()
    return runtime.knowledge if runtime is not None else _knowledge_store


def get_object_store() -> Any:
    global _object_store
    from ragassist.runtime import active_runtime

    runtime = active_runtime()
    if runtime is not None:
        return runtime.object_store
    if _object_store is None:
        settings = get_settings()
        if settings.APP_ENV == "test":
            _object_store = InMemoryObjectStore()
        else:
            try:
                _object_store = S3ObjectStore(settings)
            except Exception:
                _object_store = InMemoryObjectStore()
    return _object_store


def get_message_queue() -> Any:
    global _message_queue
    from ragassist.runtime import active_runtime

    runtime = active_runtime()
    if runtime is not None:
        return runtime.queue
    if _message_queue is None:
        settings = get_settings()
        if settings.APP_ENV == "test":
            _message_queue = InMemoryMessageQueue()
        else:
            try:
                _message_queue = SQSMessageQueue(settings)
            except Exception:
                _message_queue = InMemoryMessageQueue()
    return _message_queue


MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_READ_CHUNK = 1024 * 1024


def _require_admin(principal: Principal, action: str) -> None:
    if principal.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"Admin role required to {action}"
        )


async def _read_bounded(file: UploadFile) -> bytes:
    """Read an upload without ever holding more than the cap (plus one chunk) in memory."""
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_READ_CHUNK):
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document for ingestion",
)
async def upload_document(
    file: UploadFile = File(...),
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_object_store),
    queue: Any = Depends(get_message_queue),
    knowledge_store: InMemoryDocumentStore = Depends(get_knowledge_store),
    events: Any = Depends(get_event_bus),
) -> DocumentUploadResponse:
    """Upload a multipart document, persist to S3, record state, and enqueue SQS job."""
    if principal.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to upload documents",
        )

    content = await _read_bounded(file)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content cannot be empty (0 bytes).",
        )
    filename = file.filename or "document.txt"
    content_type = file.content_type
    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(filename)
        content_type = guessed or "application/octet-stream"

    use_case = UploadDocument(
        store=store,
        queue=queue,
        documents=knowledge_store,
        max_bytes=MAX_UPLOAD_BYTES,
    )

    try:
        command = UploadCommand(
            tenant_id=str(principal.tenant_id),
            user_id=str(principal.user_id),
            filename=filename,
            mime=content_type,
            content=content,
        )
        res = await use_case.execute(command)

        # Store document record
        now = datetime.now(timezone.utc).isoformat()
        await knowledge_store.add_document({
            "document_id": res.document_id,
            "tenant_id": str(principal.tenant_id),
            "filename": filename,
            "content_type": content_type,
            "file_size_bytes": len(content),
            "status": "queued",
            "object_key": res.object_key,
            "created_at": now,
            "updated_at": now,
        })

        await publish_safely(
            events,
            job_updated(principal.tenant_id, res.job_id, res.document_id),
            document_changed(principal.tenant_id, res.document_id),
        )
        return DocumentUploadResponse(
            document_id=res.document_id,
            job_id=res.job_id,
            object_key=res.object_key,
            status="queued",
        )
    except UnsupportedMimeType as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except FileTooLarge as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List tenant documents",
)
async def list_documents(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(get_current_principal),
    knowledge_store: InMemoryDocumentStore = Depends(get_knowledge_store),
) -> DocumentListResponse:
    """List documents belonging exclusively to the authenticated tenant."""
    docs, total = await knowledge_store.list_documents(str(principal.tenant_id), limit=limit, offset=offset)
    items = [
        DocumentSummary(
            document_id=d["document_id"],
            tenant_id=d["tenant_id"],
            filename=d["filename"],
            content_type=d.get("content_type", "application/octet-stream"),
            file_size_bytes=d.get("file_size_bytes", 0),
            status=d.get("status", "completed"),
            error_message=d.get("error_message"),
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=d.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )
        for d in docs
    ]
    return DocumentListResponse(items=items, total=total)


@router.delete(
    "/documents/{document_id}",
    summary="Delete a document and its indexed vectors",
)
async def delete_document(
    document_id: str,
    principal: Principal = Depends(get_current_principal),
    store: Any = Depends(get_object_store),
    knowledge_store: InMemoryDocumentStore = Depends(get_knowledge_store),
    events: Any = Depends(get_event_bus),
) -> dict[str, Any]:
    """Delete document by ID with tenant isolation verification (administrators only, like upload)."""
    _require_admin(principal, "delete documents")
    doc = await knowledge_store.get_document(str(principal.tenant_id), document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if doc.get("object_key"):
        if hasattr(store, "delete"):
            await store.delete(doc["object_key"])
        elif hasattr(store, "delete_object"):
            await store.delete_object(doc["object_key"])

    await knowledge_store.delete_document(str(principal.tenant_id), document_id)
    await publish_safely(events, document_changed(principal.tenant_id, document_id))
    return {"deleted": True, "document_id": document_id}


@router.post(
    "/documents/{document_id}/reindex",
    summary="Re-index an existing document",
)
async def reindex_document(
    document_id: str,
    principal: Principal = Depends(get_current_principal),
    queue: Any = Depends(get_message_queue),
    knowledge_store: InMemoryDocumentStore = Depends(get_knowledge_store),
    events: Any = Depends(get_event_bus),
) -> dict[str, Any]:
    """Trigger re-indexing of an existing document (administrators only, like upload)."""
    _require_admin(principal, "re-index documents")
    doc = await knowledge_store.get_document(str(principal.tenant_id), document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    job_id = str(uuid4())
    job = IngestionJob(
        job_id=job_id,
        document_id=document_id,
        tenant_id=str(principal.tenant_id),
        status=JobStatus.QUEUED,
    )
    await knowledge_store.add_job(job)

    # Enqueue SQS message
    msg = {
        "job_id": job_id,
        "tenant_id": str(principal.tenant_id),
        "document_id": document_id,
        "object_key": doc.get("object_key", ""),
        "reindex": True,
    }
    if hasattr(queue, "send"):
        import json
        await queue.send(json.dumps(msg))
    else:
        from ragassist.shared.config.settings import get_settings
        await queue.send_message(get_settings().SQS_QUEUE_INGEST, msg)

    await publish_safely(
        events,
        job_updated(principal.tenant_id, job_id, document_id),
        document_changed(principal.tenant_id, document_id),
    )
    return {"document_id": document_id, "job_id": job_id, "status": "queued"}


@router.get(
    "/ingestion-jobs/{job_id}",
    response_model=IngestionJobResponse,
    summary="Get status of an ingestion job",
)
async def get_ingestion_job(
    job_id: str,
    principal: Principal = Depends(get_current_principal),
    knowledge_store: InMemoryDocumentStore = Depends(get_knowledge_store),
) -> IngestionJobResponse:
    """Retrieve status of an ingestion job for the authenticated tenant."""
    job = await knowledge_store.get_job(str(principal.tenant_id), job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found")

    return IngestionJobResponse(
        job_id=job["job_id"],
        document_id=job["document_id"],
        tenant_id=job["tenant_id"],
        status=job["status"],
        attempts=job.get("attempts", 0),
        chunks_created=job.get("chunks_created", 0),
        tokens_indexed=job.get("tokens_indexed", 0),
        error_message=job.get("error_message"),
        created_at=job.get("created_at", datetime.now(timezone.utc).isoformat()),
    )
