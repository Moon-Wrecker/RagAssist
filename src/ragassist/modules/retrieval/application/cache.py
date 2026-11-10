"""Short-lived cache of hybrid retrieval results (ADR 0015).

Goal: a repeated question inside a minute does not search again. The cached value is the ranked ``Hit`` list the
retriever returned, before reranking.

Key (see ``platform/cache/keys.py``): tenant, the caller's role, a keyed hash of the normalised question, the number
of hits asked for, and the tenant's *corpus version*. The version is a random token that ``document.changed``
replaces, so uploading, re-indexing or deleting a document makes every older entry unreachable immediately; the TTL
(``CACHE_RETRIEVAL_TTL_SECONDS``) only bounds staleness if an event is lost. No content is in the key. The role is in
the key although retrieval does not filter by role today, so that if it ever does, a hit still cannot cross roles.

The key is computed once, before the search, and the result is stored under that same key: a document change that
lands while the search runs moves the version on, so a result computed against the old corpus can never be served as
if it were current.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ragassist.modules.retrieval.domain import Hit
from ragassist.platform.cache import CacheService
from ragassist.platform.cache import keys as cache_kinds


@dataclass(frozen=True)
class RetrievalLookup:
    """Outcome of a lookup: the cached hits (``None`` on a miss) and the key a fresh result must be stored under."""

    key: str
    hits: list[Hit] | None

    @property
    def hit(self) -> bool:
        return self.hits is not None


def _encode(hits: list[Hit]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": h.chunk_id,
            "document_id": h.document_id,
            "tenant_id": h.tenant_id,
            "score": h.score,
            "text": h.text,
            "heading_path": list(h.heading_path),
            "page": h.page,
            "title": h.title,
        }
        for h in hits
    ]


def _decode(rows: Any) -> list[Hit] | None:
    if not isinstance(rows, list):
        return None
    try:
        return [
            Hit(
                chunk_id=str(r["chunk_id"]),
                document_id=str(r["document_id"]),
                tenant_id=None if r["tenant_id"] is None else str(r["tenant_id"]),
                score=float(r["score"]),
                text=str(r["text"]),
                heading_path=tuple(str(p) for p in r["heading_path"]),
                page=None if r["page"] is None else int(r["page"]),
                title=str(r["title"]),
            )
            for r in rows
        ]
    except (KeyError, TypeError, ValueError):
        return None


class RetrievalResultCache:
    def __init__(self, cache: CacheService) -> None:
        self._cache = cache

    @property
    def enabled(self) -> bool:
        return self._cache.enabled

    async def lookup(self, tenant_id: object, role: str, query: str, k: int) -> RetrievalLookup:
        version = await self._cache.corpus_version(tenant_id)
        key = self._cache.keys.key(
            cache_kinds.RETRIEVAL,
            tenant_id,
            role=role,
            text=query,
            context=(str(k), version),
        )
        raw = await self._cache.get_json(cache_kinds.RETRIEVAL, key)
        return RetrievalLookup(key, _decode(raw) if raw is not None else None)

    async def store(self, lookup: RetrievalLookup, hits: list[Any]) -> bool:
        """Cache ``hits`` under the key from ``lookup``; anything that is not a ``Hit`` list is left uncached."""
        if not hits or not all(isinstance(h, Hit) for h in hits):
            return False  # an empty result is not cached: a retry after an upload must search again
        return await self._cache.set_json(
            cache_kinds.RETRIEVAL, lookup.key, _encode(hits), self._cache.ttls.retrieval
        )
