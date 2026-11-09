"""A compiled assistant graph built from fakes, for tests that go through the HTTP API.

The API resolves its graph through ``Container.get_assistant_graph``. In production that wires the real
decision chain, retriever and chat models; in tests none of those exist, so the API tests use this graph.
It is the real ``build_graph`` with scripted models, so SSE framing, state handling and approvals are the
production code paths. Tests of the container itself opt out with ``@pytest.mark.real_assistant_graph``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from fakes.retriever import FakeHit, InMemoryRetriever

from support.graph_harness import make_graph, make_kit


class AnyQueryRetriever(InMemoryRetriever):
    """Answers every non-empty query with one global passage, so a turn always has a citation."""

    async def search(  # type: ignore[override]
        self,
        query: str,
        *,
        tenant_id: object,
        k: int,
        filters: dict[str, str] | None = None,
    ) -> list[FakeHit]:
        self.calls.append({"query": query, "tenant_id": str(tenant_id), "k": k, "filters": filters})
        if not query.strip() or k <= 0:
            return []
        return [replace(row, score=1.0) for row in self._rows[:k]]


def make_api_graph() -> Any:
    kit = make_kit()
    retriever = AnyQueryRetriever()
    retriever.add(
        chunk_id="g1",
        document_id="doc-g",
        tenant_id=None,
        text="invoices are issued monthly on the first day",
        title="Billing guide",
        heading_path=("Invoices",),
        page=1,
    )
    kit.retriever = retriever
    return make_graph(kit)
