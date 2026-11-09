"""In-memory retriever: deterministic keyword overlap scoring with the same tenant rules as the
database retrievers (own tenant rows plus global rows with ``tenant_id None``).

Checked against ``RetrieverContract`` in tests/selfcheck, so the fake cannot drift from the port.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class FakeHit:
    chunk_id: str
    document_id: str
    tenant_id: str | None
    score: float
    text: str
    heading_path: tuple[str, ...] = ()
    page: int | None = None
    title: str = ""


class InMemoryRetriever:
    def __init__(self) -> None:
        self._rows: list[FakeHit] = []
        self.calls: list[dict[str, object]] = []

    def add(
        self,
        *,
        chunk_id: str,
        document_id: str,
        text: str,
        tenant_id: str | None = None,
        heading_path: tuple[str, ...] = (),
        page: int | None = None,
        title: str = "",
    ) -> None:
        self._rows.append(
            FakeHit(
                chunk_id,
                document_id,
                tenant_id and str(tenant_id),
                0.0,
                text,
                heading_path,
                page,
                title,
            )
        )

    async def search(
        self,
        query: str,
        *,
        tenant_id: object,
        k: int,
        filters: dict[str, str] | None = None,
    ) -> list[FakeHit]:
        self.calls.append({"query": query, "tenant_id": str(tenant_id), "k": k, "filters": filters})
        terms = set(query.lower().split())
        if not terms or k <= 0:
            return []
        visible = [
            row for row in self._rows if row.tenant_id is None or row.tenant_id == str(tenant_id)
        ]
        if filters and "document_id" in filters:
            visible = [row for row in visible if row.document_id == filters["document_id"]]
        scored: list[FakeHit] = []
        for row in visible:
            overlap = len(terms & set(row.text.lower().split()))
            if overlap:
                scored.append(replace(row, score=overlap / len(terms)))
        scored.sort(key=lambda hit: (-hit.score, hit.chunk_id))
        return scored[:k]
