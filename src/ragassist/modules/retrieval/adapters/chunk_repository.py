"""Chunk read adapters: PostgreSQL (row-level security) and in-memory (memory backend and tests).

Goal: load one passage for a citation, scoped to the caller's tenant plus the global rows (``tenant_id IS NULL``).
The query repeats the tenant filter that the RLS policy already enforces (defence in depth, AGENTS.md section 1.3).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from ragassist.modules.retrieval.domain import ChunkDetail
from ragassist.shared.db.scoped import ScopedDatabase

_SELECT = text(
    "SELECT c.id, c.document_id, c.tenant_id, c.text, c.heading_path, c.page, c.title, "
    "d.title AS document_title "
    "FROM chunks c LEFT JOIN documents d ON d.id = c.document_id "
    "WHERE c.id = :id AND (c.tenant_id = :tenant_id OR c.tenant_id IS NULL)"
)


def _heading_path(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return ()
    return tuple(str(part) for part in raw) if isinstance(raw, (list, tuple)) else ()


class PostgresChunkRepository:
    """Reads chunks inside a tenant-scoped transaction."""

    def __init__(self, database: ScopedDatabase) -> None:
        self._db = database

    async def get(self, tenant_id: object, chunk_id: str) -> ChunkDetail | None:
        async with self._db.scope(tenant_id) as session:
            row = (await session.execute(_SELECT, {"id": chunk_id, "tenant_id": tenant_id})).first()
        if row is None:
            return None
        return ChunkDetail(
            chunk_id=str(row.id),
            document_id=str(row.document_id),
            text=str(row.text),
            document_title=str(row.document_title or ""),
            title=str(row.title or ""),
            page=row.page,
            heading_path=_heading_path(row.heading_path),
            is_global=row.tenant_id is None,
        )


class InMemoryChunkRepository:
    """Process-local chunks, keyed by tenant (``None`` = global)."""

    def __init__(self) -> None:
        self._rows: dict[str, tuple[str | None, ChunkDetail]] = {}

    def add(self, chunk: ChunkDetail, *, tenant_id: object | None) -> None:
        self._rows[chunk.chunk_id] = (str(tenant_id) if tenant_id is not None else None, chunk)

    async def get(self, tenant_id: object, chunk_id: str) -> ChunkDetail | None:
        found = self._rows.get(chunk_id)
        if found is None:
            return None
        owner, chunk = found
        if owner is not None and owner != str(tenant_id):
            return None
        return chunk
