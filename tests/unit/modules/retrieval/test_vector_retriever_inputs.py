"""Values interpolated into SQL by the vector retriever are a closed set, never free text."""

from __future__ import annotations

import pytest

from ragassist.modules.retrieval.vector_retriever import ITERATIVE_SCAN_MODES, VectorRetriever


def build(**kwargs):  # type: ignore[no-untyped-def]
    return VectorRetriever(embedder=object(), session_factory=lambda: None, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", sorted(ITERATIVE_SCAN_MODES))
def test_the_documented_scan_modes_are_accepted(mode: str) -> None:
    assert build(iterative_scan=mode).iterative_scan == mode


@pytest.mark.parametrize("mode", ["relaxed_order'; DROP TABLE chunks; --", "fast", "RELAXED_ORDER"])
def test_any_other_scan_mode_is_rejected(mode: str) -> None:
    with pytest.raises(ValueError):
        build(iterative_scan=mode)


@pytest.mark.parametrize("table", ["chunks; DROP TABLE users", "chunks c", "public.chunks", "1chunks", ""])
def test_a_table_name_that_is_not_a_plain_identifier_is_rejected(table: str) -> None:
    with pytest.raises(ValueError):
        build(table_name=table)
