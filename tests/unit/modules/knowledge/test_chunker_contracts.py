"""Every chunker runs the shared ChunkerContract (ADR 0003). The docling variant needs its extra and
is pending until that is installed."""

from __future__ import annotations

import pytest
from support.contracts import ChunkerContract
from support.knowledge_builders import make_chunker


class TestHybridChunkerContract(ChunkerContract):
    @pytest.fixture
    def chunker(self, counter):  # type: ignore[no-untyped-def]
        return make_chunker("knowledge.chunker.hybrid", counter)


class TestRecursiveChunkerContract(ChunkerContract):
    @pytest.fixture
    def chunker(self, counter):  # type: ignore[no-untyped-def]
        return make_chunker("knowledge.chunker.recursive", counter)


class TestDoclingHybridChunkerContract(ChunkerContract):
    @pytest.fixture
    def chunker(self, counter):  # type: ignore[no-untyped-def]
        return make_chunker("knowledge.chunker.docling_hybrid", counter)
