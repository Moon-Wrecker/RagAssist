"""Keyword Retriever using PostgreSQL websearch_to_tsquery + ts_rank_cd and ParadeDB BM25.

Goal:
    Execute precise lexical keyword retrieval over document chunks using PostgreSQL Full-Text
    Search (websearch_to_tsquery and ts_rank_cd) or ParadeDB BM25, supporting boolean negation
    (minus operator) and phrase queries while guaranteeing tenant isolation and SQL safety.

Consulted References:
    - PostgreSQL Official Documentation - Full Text Search:
      https://www.postgresql.org/docs/current/textsearch-controls.html
      (Decision: use `websearch_to_tsquery('english', :query)` for natural web search syntax
      with negation and quotes; use `ts_rank_cd` cover density ranking).
    - ParadeDB pg_search Documentation:
      https://docs.paradedb.com/
      (Decision: support `text @@@ :query` and `pdb.score(id)` with graceful fallback to native FTS).
"""

from collections.abc import Callable
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from ragassist.modules.retrieval.domain import Hit
from ragassist.modules.retrieval.vector_retriever import _parse_row
from ragassist.shared.config.settings import get_settings
from ragassist.shared.db.uow import UnitOfWork

logger = structlog.get_logger(__name__)


class KeywordRetriever:
    """Sparse keyword retriever supporting PostgreSQL native FTS and ParadeDB BM25."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        backend: str | None = None,
        table_name: str = "chunks",
    ) -> None:
        self.session_factory = session_factory
        settings = get_settings()
        self.backend = (backend or getattr(settings, "KEYWORD_SEARCH_BACKEND", "fts")).lower()
        self.table_name = table_name

    async def _search_fts(
        self,
        session: AsyncSession,
        query: str,
        tenant_id: Any,
        k: int,
        filters: dict[str, Any] | None,
    ) -> list[Hit]:
        filter_clauses = ["(tenant_id = :tenant_id OR tenant_id IS NULL)"]
        filter_clauses.append("coalesce(fts, to_tsvector('english', coalesce(text, ''))) @@ websearch_to_tsquery('english', :query)")
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "query": query,
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
                ts_rank_cd(coalesce(fts, to_tsvector('english', coalesce(text, ''))), websearch_to_tsquery('english', :query)) AS score
            FROM {self.table_name}
            WHERE {where_sql}
            ORDER BY score DESC, id ASC
            LIMIT :k
        """

        result = await session.execute(text(sql), params)
        rows = result.fetchall()
        return [_parse_row(row) for row in rows]

    async def _search_paradedb(
        self,
        session: AsyncSession,
        query: str,
        tenant_id: Any,
        k: int,
        filters: dict[str, Any] | None,
    ) -> list[Hit]:
        filter_clauses = ["(tenant_id = :tenant_id OR tenant_id IS NULL)"]
        filter_clauses.append("text @@@ :query")
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "query": query,
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
                pdb.score(id) AS score
            FROM {self.table_name}
            WHERE {where_sql}
            ORDER BY score DESC, id ASC
            LIMIT :k
        """

        try:
            result = await session.execute(text(sql), params)
            rows = result.fetchall()
            return [_parse_row(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning("keyword_retriever.paradedb_failed_falling_back_to_fts", error=str(exc))
            return await self._search_fts(session, query, tenant_id, k, filters)

    async def search(
        self,
        query: str,
        *,
        tenant_id: Any,
        k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]:
        """Perform sparse keyword search."""
        if k <= 0 or not query.strip():
            return []

        async with self.session_factory() as session:
            async with UnitOfWork(session, tenant_id=tenant_id):
                if self.backend in ("paradedb", "bm25"):
                    return await self._search_paradedb(session, query, tenant_id, k, filters)
                return await self._search_fts(session, query, tenant_id, k, filters)


__all__ = ["KeywordRetriever"]
