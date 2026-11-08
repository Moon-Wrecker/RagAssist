"""Builders for the knowledge suites.

Planned classes are reached through ``need`` so a missing module skips its caller as PENDING. The
entities (Document, IngestionJob, JobStatus) and the parser output shape are the implementation team's
code, so the builders follow it: a parsed document is a ParsedDocument of Block objects (kind, text,
heading_path, page), and the chunker turns it into ChunkDraft objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from fakes.documents import InMemoryDocumentRepository
from fakes.tokens import WhitespaceCounter

from support.specs import need


@dataclass
class Tenant:
    tenant_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = field(default_factory=lambda: str(uuid4()))


def block(kind: str, text: str, heading_path: tuple[str, ...] = (), page: int | None = None) -> Any:
    """One structural block, as the Parser port produces it (the domain's Block)."""
    return need("knowledge.Block")(kind, text, heading_path, page)


def parsed_document(blocks: list[Any], title: str = "Billing guide") -> Any:
    """A parsed document (the domain's ParsedDocument): what the Chunker port takes."""
    return need("knowledge.ParsedDocument")(title=title, blocks=blocks)


def make_chunker(key: str, counter: WhitespaceCounter, **overrides: Any) -> Any:
    """Build a planned chunker with the test tokenizer and a small budget (40 tokens)."""
    cls = need(key)
    kwargs: dict[str, Any] = {"max_tokens": 40, "overlap_tokens": 0, "tokenizer": counter}
    if key.endswith("hybrid"):
        kwargs["merge_peers"] = True
    if key.endswith("docling_hybrid"):
        kwargs.pop("overlap_tokens")
    kwargs.update(overrides)
    return cls(**kwargs)


def make_message(
    *, job_id: str, tenant_id: str, object_key: str, document_id: str | None = None
) -> dict[str, Any]:
    """The queue body the upload use case sends (the MessageQueue port takes dict bodies)."""
    body: dict[str, Any] = {"job_id": job_id, "tenant_id": tenant_id, "object_key": object_key}
    if document_id is not None:
        body["document_id"] = document_id
    return body


def make_document(
    tenant: Tenant, document_id: UUID, *, s3_key: str, content_type: str = "text/markdown"
) -> Any:
    document_cls = need("knowledge.Document")
    return document_cls(
        id=document_id,
        created_at=datetime.now(UTC),
        tenant_id=tenant.tenant_id,
        filename="guide.md",
        content_type=content_type,
        file_size_bytes=0,
        s3_key=s3_key,
        content_hash="0" * 64,
    )


async def seed_queued_job(
    documents: InMemoryDocumentRepository,
    tenant: Tenant,
    store: Any,
    content: bytes | None,
    *,
    content_type: str = "text/markdown",
) -> SimpleNamespace:
    """A queued job and its document, plus the stored object: the state after a successful upload.
    Pass ``content=None`` to leave the object missing."""
    job_id, document_id = uuid4(), uuid4()
    object_key = f"tenants/{tenant.tenant_id}/documents/{document_id}/guide.md"
    job_cls = need("knowledge.IngestionJob")
    status = need("knowledge.JobStatus").QUEUED
    job = job_cls(
        id=job_id,
        created_at=datetime.now(UTC),
        document_id=document_id,
        tenant_id=tenant.tenant_id,
        status=status,
    )
    await documents.add_document(
        make_document(tenant, document_id, s3_key=object_key, content_type=content_type)
    )
    await documents.add_job(job)
    if content is not None:
        await store.put_object(object_key, content, content_type=content_type)
    return SimpleNamespace(
        job_id=str(job_id),
        document_id=str(document_id),
        object_key=object_key,
        job=job,
        tenant_id=tenant.tenant_id,
        content=content,
    )
