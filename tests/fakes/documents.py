"""In-memory document repository for ingestion tests.

Stands in for the knowledge module's persistence port until the repository adapter exists; its contract
is written in docs/testing.md (interface appendix) and it must be replaced by the real adapter's contract
suite when that lands. Entities are the implementation team's frozen dataclasses, so status changes
are made with ``dataclasses.replace``, the same way the domain expects.

Every write records the tenant it was made for, so tenant-context tests can check that a worker only
writes for the tenant named in its message. ``transaction()`` snapshots the state and restores it when
the block raises, mirroring a database rollback. ``fail_on(op, error)`` makes the next call of ``op``
raise before it changes anything.
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any


def _key(obj_id: Any) -> str:
    return str(obj_id)


@dataclass
class InMemoryDocumentRepository:
    documents: dict[str, Any] = field(default_factory=dict)
    jobs: dict[str, Any] = field(default_factory=dict)
    chunks: dict[str, list[Any]] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)
    writes: list[tuple[str, str]] = field(default_factory=list)
    _failures: dict[str, BaseException] = field(default_factory=dict)

    def fail_on(self, operation: str, error: BaseException) -> None:
        self._failures[operation] = error

    def _check(self, operation: str) -> None:
        error = self._failures.pop(operation, None)
        if error is not None:
            raise error

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        snapshot = copy.deepcopy(
            (self.documents, self.jobs, self.chunks, self.attempts, self.writes)
        )
        try:
            yield
        except BaseException:
            self.documents, self.jobs, self.chunks, self.attempts, self.writes = snapshot
            raise

    async def add_document(self, document: Any) -> None:
        self._check("add_document")
        self.documents[_key(document.id)] = document
        self.writes.append((str(document.tenant_id), "add_document"))

    async def get_document(self, document_id: str) -> Any | None:
        self._check("get_document")
        return self.documents.get(_key(document_id))

    async def add_job(self, job: Any) -> None:
        self._check("add_job")
        self.jobs[_key(job.id)] = job
        self.writes.append((str(job.tenant_id), "add_job"))

    async def get_job(self, job_id: str) -> Any | None:
        self._check("get_job")
        return self.jobs.get(_key(job_id))

    async def claim_job(self, job_id: str, *, tenant_id: str) -> bool:
        """Atomic queued -> parsing. False when the job is missing or not queued (another worker has it)."""
        self._check("claim_job")
        job = self.jobs.get(_key(job_id))
        if job is None or job.status != "queued":
            return False
        self.jobs[_key(job_id)] = replace(job, status="parsing")
        self.attempts[_key(job_id)] = self.attempts.get(_key(job_id), 0) + 1
        self.writes.append((str(tenant_id), "claim_job"))
        return True

    async def save_job(self, job: Any, *, tenant_id: str) -> None:
        self._check("save_job")
        self.jobs[_key(job.id)] = job
        self.writes.append((str(tenant_id), "save_job"))

    async def replace_chunks(
        self, document_id: str, chunks: Iterable[Any], *, tenant_id: str
    ) -> None:
        """All-or-nothing swap: the old chunks are replaced only when the new ones are stored."""
        self._check("replace_chunks")
        self.chunks[_key(document_id)] = list(chunks)
        self.writes.append((str(tenant_id), "replace_chunks"))

    async def chunks_for(self, document_id: str) -> list[Any]:
        return list(self.chunks.get(_key(document_id), []))

    def attempts_for(self, job_id: str) -> int:
        return self.attempts.get(_key(job_id), 0)
