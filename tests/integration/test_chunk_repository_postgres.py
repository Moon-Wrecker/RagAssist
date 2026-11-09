"""PostgresChunkRepository against a real database: own-tenant and global chunks are readable, another tenant's are not.

The query repeats the tenant filter and the row-level-security policy enforces it a second time.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ragassist.modules.retrieval.adapters.chunk_repository import PostgresChunkRepository
from ragassist.shared.db.scoped import ScopedDatabase

from .conftest import Seed


@pytest.fixture
def repo(app_engines: Callable[..., AsyncEngine]) -> PostgresChunkRepository:
    return PostgresChunkRepository(ScopedDatabase(async_sessionmaker(app_engines(), expire_on_commit=False)))


async def add_chunk(admin_engine: AsyncEngine, tenant_id, body: str, *, title: str = "Refunds") -> str:  # type: ignore[no-untyped-def]
    document_id, chunk_id = uuid4(), str(uuid4())
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO documents (id, tenant_id, title, filename, content_type, object_key) "
                "VALUES (:id, :tenant, 'Billing FAQ', 'faq.md', 'text/markdown', :key)"
            ),
            {"id": document_id, "tenant": tenant_id, "key": f"seed/{document_id}"},
        )
        await conn.execute(
            text(
                "INSERT INTO chunks (id, tenant_id, document_id, text, heading_path, page, title) "
                "VALUES (:id, :tenant, :doc, :body, CAST(:heading AS jsonb), 3, :title)"
            ),
            {
                "id": chunk_id,
                "tenant": tenant_id,
                "doc": document_id,
                "body": body,
                "heading": '["Billing", "Refunds"]',
                "title": title,
            },
        )
    return chunk_id


@pytest.fixture(autouse=True)
async def _empty(seed: Seed, admin_engine: AsyncEngine) -> None:
    async with admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE chunks, documents CASCADE"))


async def test_an_own_chunk_is_returned_with_its_provenance(
    seed: Seed, admin_engine: AsyncEngine, repo: PostgresChunkRepository
) -> None:
    chunk_id = await add_chunk(admin_engine, seed.tenant_a, "Refunds take 5 days.")
    chunk = await repo.get(seed.tenant_a, chunk_id)
    assert chunk is not None
    assert (chunk.text, chunk.page, chunk.title, chunk.document_title) == (
        "Refunds take 5 days.",
        3,
        "Refunds",
        "Billing FAQ",
    )
    assert chunk.heading_path == ("Billing", "Refunds") and chunk.is_global is False


async def test_a_global_chunk_is_readable_by_any_tenant(
    seed: Seed, admin_engine: AsyncEngine, repo: PostgresChunkRepository
) -> None:
    chunk_id = await add_chunk(admin_engine, None, "Shared guidance.")
    for tenant in (seed.tenant_a, seed.tenant_b):
        chunk = await repo.get(tenant, chunk_id)
        assert chunk is not None and chunk.is_global is True


async def test_another_tenants_chunk_and_an_unknown_id_are_not_found(
    seed: Seed, admin_engine: AsyncEngine, repo: PostgresChunkRepository
) -> None:
    chunk_id = await add_chunk(admin_engine, seed.tenant_b, "Tenant B only.")
    assert await repo.get(seed.tenant_a, chunk_id) is None
    assert await repo.get(seed.tenant_a, "no-such-chunk") is None
