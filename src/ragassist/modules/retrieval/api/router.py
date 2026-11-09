"""FastAPI router for reading the passage behind a citation.

Goal: ``GET /v1/chunks/{chunk_id}`` returns a chunk's text and provenance to any signed-in user of the tenant,
including the global (shared knowledge) rows, and ``404`` for anything else, so another tenant's chunk is
indistinguishable from an unknown id.

Consulted: FastAPI dependency injection; docs/api/sse-contract.md ("Passages").
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ragassist.modules.retrieval.adapters.chunk_repository import InMemoryChunkRepository
from ragassist.modules.retrieval.application import GetChunk
from ragassist.shared.security.deps import get_current_principal
from ragassist.shared.security.jwt import Principal

router = APIRouter(tags=["Retrieval"])

_memory_chunks = InMemoryChunkRepository()


class ChunkResponse(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str = ""
    title: str = ""
    text: str
    page: int | None = None
    heading_path: list[str] = Field(default_factory=list)
    is_global: bool = False


def get_chunk_reader() -> Any:
    """The Postgres reader when the runtime is started (PERSISTENCE_BACKEND=postgres), else the in-memory one."""
    from ragassist.runtime import active_runtime

    runtime = active_runtime()
    return runtime.chunks if runtime is not None else _memory_chunks


@router.get(
    "/chunks/{chunk_id}",
    response_model=ChunkResponse,
    summary="Get the passage behind a citation",
)
async def get_chunk(
    chunk_id: str,
    principal: Principal = Depends(get_current_principal),
    reader: Any = Depends(get_chunk_reader),
) -> ChunkResponse:
    """Text and metadata of one chunk of the caller's tenant or a global one."""
    chunk = await GetChunk(reader).execute(principal.tenant_id, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    return ChunkResponse(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        document_title=chunk.document_title,
        title=chunk.title,
        text=chunk.text,
        page=chunk.page,
        heading_path=list(chunk.heading_path),
        is_global=chunk.is_global,
    )
