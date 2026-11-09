"""Fixtures for the knowledge (ingestion) suites. Everything planned is reached through ``need``;
the fakes are the ones in tests/fakes, so only the module under test is pending."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fakes.clock import FakeClock
from fakes.documents import InMemoryDocumentRepository
from fakes.embeddings import FakeEmbeddingProvider
from fakes.tokens import WhitespaceCounter
from support.knowledge_builders import Tenant
from support.specs import need

ALLOWED_MIMES = frozenset({"text/markdown", "text/html", "text/csv", "application/pdf"})
ONE_MIB = 1024 * 1024


@pytest.fixture
def counter() -> WhitespaceCounter:
    return WhitespaceCounter()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    return need("storage.memory")()  # production in-memory adapter (fakes are for providers only)


@pytest.fixture
def queue():  # type: ignore[no-untyped-def]
    return need("queue.memory")()  # production in-memory adapter


@pytest.fixture
def documents() -> InMemoryDocumentRepository:
    return InMemoryDocumentRepository()


@pytest.fixture
def embedder() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dimension=8)


@pytest.fixture
def tenant() -> Tenant:
    return Tenant()


@pytest.fixture
def upload_factory(
    store: Any, queue: Any, documents: InMemoryDocumentRepository
) -> Callable[..., Any]:
    """Build the planned ``UploadDocument`` use case with fakes for every collaborator."""

    def build(**overrides: Any) -> Any:
        upload_cls = need("knowledge.UploadDocument")
        kwargs: dict[str, Any] = {
            "store": store,
            "queue": queue,
            "documents": documents,
            "max_bytes": ONE_MIB,
            "allowed_mimes": ALLOWED_MIMES,
        }
        kwargs.update(overrides)
        return upload_cls(**kwargs)

    return build


@pytest.fixture
def command_factory() -> Callable[..., Any]:
    def build(tenant: Tenant, **overrides: Any) -> Any:
        command_cls = need("knowledge.UploadCommand")
        kwargs: dict[str, Any] = {
            "tenant_id": tenant.tenant_id,
            "user_id": tenant.user_id,
            "filename": "guide.md",
            "mime": "text/markdown",
            "content": b"# Guide\n\nHello.",
        }
        kwargs.update(overrides)
        return command_cls(**kwargs)

    return build
