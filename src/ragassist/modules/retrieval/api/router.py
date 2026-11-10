"""FastAPI router for reading the passage behind a citation.

Goal: ``GET /v1/chunks/{chunk_id}`` returns a chunk's text and provenance to any signed-in user of the tenant,
including the global (shared knowledge) rows, and ``404`` for anything else, so another tenant's chunk is
indistinguishable from an unknown id.

HTTP caching (ADR 0015): the answer carries a strong ``ETag`` and ``Cache-Control: private, max-age=N`` so the browser
reuses a passage it already read; a conditional request is answered with ``304`` only **after** the chunk was loaded
for the caller's tenant, so another tenant's id still gets the same ``404`` and no ``304`` can confirm a chunk exists.

Consulted: FastAPI dependency injection; docs/api/sse-contract.md ("Passages"); RFC 9111 and RFC 9110 (ETag,
If-None-Match).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ragassist.modules.retrieval.adapters.chunk_repository import InMemoryChunkRepository
from ragassist.modules.retrieval.application import GetChunk
from ragassist.shared.config.settings import get_settings
from ragassist.shared.http_cache import (
    etag_of,
    if_none_match_matches,
    private_cache_control,
    validator_headers,
)
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
    # The conditional request (If-None-Match -> 304) is read from ``request`` rather than declared as a header
    # parameter, so the published OpenAPI schema (and the generated frontend types) stay unchanged. It is
    # documented in docs/api/sse-contract.md ("HTTP caching").
)
async def get_chunk(
    chunk_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(get_current_principal),
    reader: Any = Depends(get_chunk_reader),
) -> Any:
    """Text and metadata of one chunk of the caller's tenant or a global one."""
    chunk = await GetChunk(reader).execute(principal.tenant_id, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    body = ChunkResponse(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        document_title=chunk.document_title,
        title=chunk.title,
        text=chunk.text,
        page=chunk.page,
        heading_path=list(chunk.heading_path),
        is_global=chunk.is_global,
    )
    etag = etag_of(body.model_dump_json().encode("utf-8"))
    headers = validator_headers(etag, private_cache_control(get_settings().CACHE_HTTP_MAX_AGE_SECONDS))
    if if_none_match_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers.update(headers)
    return body
