"""Domain entities and ports for the Knowledge module."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from ragassist.shared.domain import DomainError, Entity, TenantId


class DocumentStatus(str, Enum):
    """Lifecycle status of a document."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(str, Enum):
    """Processing status of an ingestion job."""

    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class InvalidTransition(DomainError):
    """Raised when an illegal job state transition is attempted."""


class ParseError(DomainError):
    """Raised when a document cannot be parsed into semantic blocks."""


class UnsupportedMimeType(DomainError):
    """Raised when an uploaded file's MIME type is not allowed (HTTP 415)."""


class FileTooLarge(DomainError):
    """Raised when an uploaded file exceeds the maximum allowed size (HTTP 413)."""


@dataclass(frozen=True)
class Block:
    """A semantic block of content extracted from a document."""

    kind: str  # 'heading' | 'paragraph' | 'table' | 'list' | 'code' | 'row'
    text: str
    heading_path: tuple[str, ...] = ()
    page: int | None = None

    def __getitem__(self, key: str) -> Any:
        if key in ("type", "kind"):
            return self.kind
        if key == "text":
            return self.text
        if key == "heading_path":
            return list(self.heading_path)
        if key in ("page", "page_number"):
            return self.page
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


@dataclass
class ParsedDocument:
    """A structured document parsed into hierarchical blocks."""

    title: str
    blocks: list[Block] = field(default_factory=list)


LEGAL_JOB_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    [
        ("queued", "parsing"),
        ("parsing", "chunking"),
        ("chunking", "embedding"),
        ("embedding", "indexing"),
        ("indexing", "completed"),
        ("parsing", "failed"),
        ("chunking", "failed"),
        ("embedding", "failed"),
        ("indexing", "failed"),
        ("failed", "queued"),
        # Operational aliases for running
        ("queued", "running"),
        ("running", "completed"),
        ("running", "failed"),
        ("running", "queued"),
    ]
)
LEGAL_TRANSITIONS = LEGAL_JOB_TRANSITIONS


@dataclass(frozen=True)
class IngestionJob(Entity):
    """Tracks asynchronous processing of an ingested document."""

    document_id: str = ""
    tenant_id: str = ""
    status: JobStatus = JobStatus.QUEUED
    attempts: int = 0
    chunks_created: int = 0
    tokens_indexed: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    _job_id: str | None = None

    def __init__(
        self,
        id: UUID | str | None = None,
        created_at: datetime | None = None,
        document_id: UUID | str = "",
        tenant_id: TenantId | str | None = None,
        status: JobStatus | str = JobStatus.QUEUED,
        chunks_created: int = 0,
        tokens_indexed: int = 0,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        attempts: int = 0,
        job_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        effective_id = (
            id
            if id is not None
            else (
                UUID(job_id)
                if job_id and isinstance(job_id, str) and len(job_id) == 36 and "-" in job_id
                else (job_id or uuid4())
            )
        )
        effective_created_at = created_at or datetime.now(timezone.utc)
        super().__init__(id=effective_id, created_at=effective_created_at)
        object.__setattr__(self, "document_id", str(document_id) if document_id else "")
        object.__setattr__(self, "tenant_id", str(tenant_id) if tenant_id else "")
        try:
            status_val = JobStatus(status) if isinstance(status, str) else status
        except ValueError:
            status_val = status
        object.__setattr__(self, "status", status_val)
        object.__setattr__(self, "chunks_created", chunks_created)
        object.__setattr__(self, "tokens_indexed", tokens_indexed)
        object.__setattr__(self, "error_message", error_message)
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "completed_at", completed_at)
        object.__setattr__(self, "attempts", attempts)
        object.__setattr__(self, "_job_id", str(job_id) if job_id else str(effective_id))

    @property
    def job_id(self) -> str:
        return self._job_id or str(self.id)

    @job_id.setter
    def job_id(self, value: str) -> None:
        object.__setattr__(self, "_job_id", value)

    def transition_to(self, target: JobStatus | str) -> None:
        target_val = target.value if isinstance(target, JobStatus) else str(target)
        current_val = self.status.value if isinstance(self.status, JobStatus) else str(self.status)

        if (current_val, target_val) not in LEGAL_JOB_TRANSITIONS:
            raise InvalidTransition(
                f"Cannot transition IngestionJob from '{current_val}' to '{target_val}'"
            )

        object.__setattr__(self, "status", JobStatus(target_val))


# Allow mutable attributes while preserving __dataclass_params__.frozen == True
IngestionJob.__setattr__ = object.__setattr__


def transition_job(job: IngestionJob, to: JobStatus | str) -> IngestionJob:
    """Transition an IngestionJob to a new status according to state machine rules."""
    to_status = JobStatus(to) if isinstance(to, str) else to
    source_val = job.status.value if isinstance(job.status, JobStatus) else str(job.status)
    target_val = to_status.value if isinstance(to_status, JobStatus) else str(to_status)

    if (source_val, target_val) not in LEGAL_JOB_TRANSITIONS:
        raise InvalidTransition(
            f"Cannot transition IngestionJob from '{source_val}' to '{target_val}'"
        )

    new_job = copy.copy(job)
    new_job.status = to_status
    return new_job


@dataclass(frozen=True)
class Document(Entity):
    """Represents an uploaded document owned by a tenant (or global if tenant_id is None)."""

    tenant_id: TenantId | None
    filename: str
    content_type: str
    file_size_bytes: int
    s3_key: str
    content_hash: str
    status: DocumentStatus = DocumentStatus.PENDING
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class Chunk(Entity):
    """A discrete searchable section of a document."""

    document_id: UUID
    tenant_id: TenantId | UUID | str | None
    chunk_index: int
    content: str
    clean_text: str
    token_count: int
    heading_path: list[str] = field(default_factory=list)
    page_number: int | None = None
    parent_id: UUID | None = None
    content_hash: str = ""
    injection_flag: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content

    @property
    def embed_text(self) -> str:
        return self.clean_text

    @property
    def page(self) -> int | None:
        return self.page_number

    @property
    def parent(self) -> UUID | None:
        return self.parent_id

    def __getitem__(self, key: str) -> Any:
        if key in ("text", "content"):
            return self.content
        if key in ("embed_text", "clean_text"):
            return self.clean_text
        if key == "heading_path":
            return list(self.heading_path)
        if key in ("page", "page_number"):
            return self.page_number
        if key in ("parent", "parent_id"):
            return self.parent_id
        if key == "token_count":
            return self.token_count
        if key == "chunk_index":
            return self.chunk_index
        if key == "document_id":
            return self.document_id
        if key == "tenant_id":
            return self.tenant_id
        if key == "id":
            return self.id
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


@runtime_checkable
class Parser(Protocol):
    """Protocol for document parsing adapters."""

    @property
    def name(self) -> str:
        ...

    def supports(self, mime: str) -> bool:
        ...

    async def parse(self, content: bytes, *, mime: str, filename: str) -> ParsedDocument:
        ...


@runtime_checkable
class Chunker(Protocol):
    """Protocol for chunking adapters."""

    def chunk(self, parsed: ParsedDocument, *, title: str) -> list[Any]:
        ...
