"""The public retrieval facade (PROJECT.md "Interface Contracts" section 4).

``RetrievalService.retrieve(tenant_id, query, top_k=6) -> list[RetrievedChunk]`` is what the agent core
depends on, so it is checked against the contract itself, not against the internal retrievers.

Open conflict C-R1: ``RetrievedChunk.heading_path`` is ``str | None`` in PROJECT.md, while the domain
``Chunk.heading_path`` is a list. The tests accept either form, and the decision is recorded in
``.agents/teamwork/test_writer_unit_suites/BRIEFING.md``.
"""

from __future__ import annotations

import inspect
import uuid
from dataclasses import fields, is_dataclass

import pytest
from support.specs import need

pytestmark = pytest.mark.unit

TENANT = uuid.UUID("a0000000-0000-0000-0000-00000000000a")
REQUIRED_FIELDS = {
    "chunk_id",
    "document_id",
    "content",
    "score",
    "heading_path",
    "page_number",
    "metadata",
}


def _field_names(dto) -> set[str]:  # type: ignore[no-untyped-def]
    if is_dataclass(dto):
        return {f.name for f in fields(dto)}
    return set(getattr(dto, "model_fields", {}))


class TestRetrievedChunkDto:
    def test_the_dto_carries_every_field_of_the_contract(self) -> None:
        assert _field_names(need("retrieval.RetrievedChunk")) >= REQUIRED_FIELDS


class TestRetrievalServiceProtocol:
    def test_retrieve_takes_tenant_query_and_top_k_with_a_default_of_six(self) -> None:
        method = need("retrieval.RetrievalService").retrieve
        params = inspect.signature(method).parameters
        assert list(params)[1:4] == ["tenant_id", "query", "top_k"]
        assert params["top_k"].default == 6

    def test_retrieve_is_asynchronous(self) -> None:
        assert inspect.iscoroutinefunction(need("retrieval.RetrievalService").retrieve)
