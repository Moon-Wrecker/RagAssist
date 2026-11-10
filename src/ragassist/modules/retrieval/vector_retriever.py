"""Vector Retriever using pgvector cosine similarity with iterative_scan and tenant isolation.

Goal:
    Retrieve top-k nearest semantic chunks from PostgreSQL using pgvector cosine distance,
    with pgvector >= 0.8.0 HNSW iterative scanning to guarantee high recall under selective
    metadata filtering, while strictly isolating tenant data via PostgreSQL RLS and UnitOfWork.

Consulted References:
    - pgvector official docs: https://github.com/pgvector/pgvector
      (Decision: use `<=>` cosine distance, `SET LOCAL hnsw.iterative_scan = 'relaxed_order'`,
      and query vector casting via `CAST(:query_vector AS vector)`).
    - ADR 0001: PostgreSQL + pgvector for Unified Multi-Tenant Storage & Checkpoints.
    - ADR 0002: Row-Level Security and Transactional Context Isolation.
"""

from collections.abc import Callable
import re
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from ragassist.modules.retrieval.domain import Hit
from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.shared.config.settings import get_settings
from ragassist.shared.db.uow import UnitOfWork

logger = structlog.get_logger(__name__)


def _extract_title(title: str | None, embed_text: str | None) -> str:
    """Extract document title from title field or embed_text header."""
    if title:
        return title
    if embed_text and embed_text.startswith("[Document: "):
        end = embed_text.find(" | Section:")
        if end != -1:
            return embed_text[len("[Document: "):end].strip()
        end = embed_text.find("]")
        if end != -1:
            return embed_text[len("[Document: "):end].strip()
    return ""


def _parse_row(row: Any) -> Hit:
    """Parse a SQLAlchemy Row, mapping or dict into a Hit entity."""
    if hasattr(row, "_mapping"):
        mapping: Any = row._mapping
    elif isinstance(row, dict):
        mapping = row
    else:
        mapping = None

    if mapping is not None:
        chunk_id = str(mapping["id"])
        doc_id = str(mapping["document_id"])
        tid = str(mapping["tenant_id"]) if mapping.get("tenant_id") is not None else None
        text_val = str(mapping["text"])
        embed_text_val = str(mapping["embed_text"]) if mapping.get("embed_text") is not None else None
        raw_heading = mapping.get("heading_path")
        heading_tuple = tuple(raw_heading) if raw_heading else ()
        page_val = mapping.get("page")
        raw_title = mapping.get("title")
        title_val = _extract_title(raw_title, embed_text_val)
        score_val = float(mapping["score"])
    else:
        chunk_id = str(row[0])
        doc_id = str(row[1])
        tid = str(row[2]) if row[2] is not None else None
        text_val = str(row[3])
        embed_text_val = str(row[4]) if row[4] is not None else None
        raw_heading = row[5]
        heading_tuple = tuple(raw_heading) if raw_heading else ()
        page_val = row[6]
        raw_title = row[7]
        title_val = _extract_title(raw_title, embed_text_val)
        score_val = float(row[8])

    return Hit(
        chunk_id=chunk_id,
        document_id=doc_id,
        tenant_id=tid,
        score=score_val,
        text=text_val,
        heading_path=heading_tuple,
        page=int(page_val) if page_val is not None else None,
        title=title_val,
    )


#: pgvector ``hnsw.iterative_scan`` values this retriever accepts (the value is interpolated into SET LOCAL).
ITERATIVE_SCAN_MODES = frozenset({"off", "relaxed_order", "strict_order"})
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class VectorRetriever:
    """Dense vector retriever using pgvector HNSW index scans and strict tenant isolation."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        session_factory: Callable[[], AsyncSession],
        iterative_scan: str | None = None,
        table_name: str = "chunks",
    ) -> None:
        self.embedder = embedder
        self.session_factory = session_factory
        settings = get_settings()
        self.iterative_scan = iterative_scan or getattr(settings, "VECTOR_SEARCH_ITERATIVE_SCAN", "relaxed_order")
        if self.iterative_scan not in ITERATIVE_SCAN_MODES:
            raise ValueError(f"iterative_scan must be one of {sorted(ITERATIVE_SCAN_MODES)}")
        if not _IDENTIFIER.match(table_name):
            raise ValueError("table_name must be a plain SQL identifier")
        self.table_name = table_name

    async def search(
        self,
        query: str,
        *,
        tenant_id: Any,
        k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]:
        """Search nearest chunks by cosine similarity."""
        if k <= 0 or not query.strip():
            return []

        # Generate query embedding vector
        # With the cache on (ADR 0015) the service answers repeats for this tenant from memory; any other embedder
        # (or a service without a cache) takes the plain path.
        embed_for_tenant = getattr(self.embedder, "embed_query_for", None)
        if embed_for_tenant is not None:
            query_vector = await embed_for_tenant(tenant_id, query)
        else:
            query_vector = await self.embedder.embed_query(query)
        vector_str = "[" + ",".join(str(float(x)) for x in query_vector) + "]"

        filter_clauses = ["(tenant_id = :tenant_id OR tenant_id IS NULL)"]
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "query_vector": vector_str,
            "k": k,
        }

        if filters and "document_id" in filters:
            filter_clauses.append("CAST(document_id AS text) = :filter_document_id")
            params["filter_document_id"] = str(filters["document_id"])

        where_sql = " AND ".join(filter_clauses)
        sql = f"""
            SELECT
                id,
                document_id,
                tenant_id,
                text,
                embed_text,
                heading_path,
                page,
                title,
                1.0 - (embedding <=> CAST(:query_vector AS vector)) AS score
            FROM {self.table_name}
            WHERE {where_sql}
            ORDER BY embedding <=> CAST(:query_vector AS vector) ASC
            LIMIT :k
        """

        async with self.session_factory() as session:
            async with UnitOfWork(session, tenant_id=tenant_id):
                # Enable iterative index scan if supported by pgvector
                if self.iterative_scan != "off":
                    try:
                        await session.execute(
                            text(f"SET LOCAL hnsw.iterative_scan = '{self.iterative_scan}'")
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("vector_retriever.iterative_scan_skipped", error=str(exc))

                result = await session.execute(text(sql), params)
                rows = result.fetchall()

        return [_parse_row(row) for row in rows]


__all__ = ["VectorRetriever"]
