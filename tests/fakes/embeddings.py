"""Deterministic fake embedding provider implementing the ``EmbeddingProvider`` port.

Vectors are unit-length, derived from a SHA-256 stream of the text, so identical text always maps
to the identical vector and different texts are (almost surely) far apart. No network, no model.
"""

from __future__ import annotations

import hashlib
import math

from langchain_core.embeddings import Embeddings


def vector_for(text: str, dimension: int) -> list[float]:
    values: list[float] = []
    counter = 0
    while len(values) < dimension:
        digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
        values.extend((byte / 255.0) * 2.0 - 1.0 for byte in digest)
        counter += 1
    vector = values[:dimension]
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class _HashEmbeddings(Embeddings):
    def __init__(self, dimension: int) -> None:
        self._dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector_for(t, self._dimension) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return vector_for(text, self._dimension)


class FakeEmbeddingProvider:
    """Records every call so tests can assert batching and call counts."""

    def __init__(self, dimension: int = 8, *, name: str = "fake", fail_times: int = 0) -> None:
        self._dimension = dimension
        self._name = name
        self._failures_left = fail_times
        self.document_batches: list[list[str]] = []
        self.queries: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def dimension(self) -> int:
        return self._dimension

    def _maybe_fail(self) -> None:
        if self._failures_left > 0:
            self._failures_left -= 1
            raise RuntimeError(f"{self._name}: injected embedding failure")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._maybe_fail()
        self.document_batches.append(list(texts))
        return [vector_for(t, self._dimension) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        self._maybe_fail()
        self.queries.append(text)
        return vector_for(text, self._dimension)

    def as_langchain_embeddings(self) -> Embeddings:
        return _HashEmbeddings(self._dimension)
