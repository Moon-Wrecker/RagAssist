"""Vector and keyword retrieval against real PostgreSQL + pgvector (plan section 3: pgvector >= 0.8 with
iterative index scans; FTS for keyword search). Uses the integration fixtures: a seeded database, the
superuser engine for seeding, and the non-superuser app engine for the retriever under test.

Needs the knowledge persistence model (ChunkModel) and the migrations; until then the module is PENDING.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fakes.embeddings import FakeEmbeddingProvider, vector_for
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from support.specs import need

pytestmark = pytest.mark.integration

DIM = 1536  # EMBEDDING_DIMENSION default; the chunk_embeddings column is vector(1536)


async def insert_chunk(
    admin_engine: AsyncEngine,
    *,
    tenant_id,
    document_id,
    text_value: str,
    title: str = "Guide",
    heading: str = "Section",
) -> str:  # type: ignore[no-untyped-def]
    chunk_model = need("knowledge.ChunkModel")
    chunk_id = str(uuid4())
    async with admin_engine.begin() as conn:  # a chunk belongs to a document (foreign key)
        await conn.execute(
            text(
                "INSERT INTO documents (id, tenant_id, title, filename, content_type, object_key) "
                "VALUES (:id, :tenant, :title, 'seed.md', 'text/markdown', :key) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": document_id, "tenant": tenant_id, "title": title, "key": f"seed/{document_id}"},
        )
    async with AsyncSession(admin_engine) as session:
        session.add(
            chunk_model(
                id=chunk_id,
                tenant_id=tenant_id,
                document_id=document_id,
                text=text_value,
                embed_text=f"[Document: {title} | Section: {heading}]\n{text_value}",
                heading_path=[heading],
                embedding=vector_for(text_value, DIM),
            )
        )
        await session.commit()
    return chunk_id


@pytest.fixture
def embedder() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dimension=DIM)


@pytest.fixture(autouse=True)
async def _empty_chunk_table(seed, admin_engine: AsyncEngine) -> None:  # type: ignore[no-untyped-def]
    """Chunks are not owned by the seed's tenants, so clear them before every test."""
    table = need("knowledge.ChunkModel").__table__.name
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {table} CASCADE"))


class TestVectorRetrieval:
    async def test_the_closest_chunk_ranks_first(
        self, seed, admin_engine, app_engines, embedder
    ) -> None:  # type: ignore[no-untyped-def]
        doc = uuid4()
        target = await insert_chunk(
            admin_engine,
            tenant_id=seed.tenant_a,
            document_id=doc,
            text_value="zanzibar pricing tiers",
        )
        await insert_chunk(
            admin_engine,
            tenant_id=seed.tenant_a,
            document_id=doc,
            text_value="quokka habitat notes",
        )
        retriever = need("retrieval.VectorRetriever")(
            embedder=embedder, session_factory=async_sessionmaker(app_engines())
        )
        hits = await retriever.search("zanzibar pricing tiers", tenant_id=seed.tenant_a, k=2)
        assert hits[0].chunk_id == target

    async def test_top_k_is_respected(self, seed, admin_engine, app_engines, embedder) -> None:  # type: ignore[no-untyped-def]
        doc = uuid4()
        for i in range(5):
            await insert_chunk(
                admin_engine,
                tenant_id=seed.tenant_a,
                document_id=doc,
                text_value=f"chunk number {i}",
            )
        retriever = need("retrieval.VectorRetriever")(
            embedder=embedder, session_factory=async_sessionmaker(app_engines())
        )
        assert len(await retriever.search("chunk number", tenant_id=seed.tenant_a, k=3)) == 3

    async def test_another_tenant_never_sees_the_chunk(
        self, seed, admin_engine, app_engines, embedder
    ) -> None:  # type: ignore[no-untyped-def]
        await insert_chunk(
            admin_engine,
            tenant_id=seed.tenant_a,
            document_id=uuid4(),
            text_value="zanzibar secret plan",
        )
        retriever = need("retrieval.VectorRetriever")(
            embedder=embedder, session_factory=async_sessionmaker(app_engines())
        )
        hits = await retriever.search("zanzibar secret plan", tenant_id=seed.tenant_b, k=5)
        assert all("zanzibar" not in hit.text for hit in hits)

    async def test_global_documents_are_visible_to_every_tenant(
        self, seed, admin_engine, app_engines, embedder
    ) -> None:  # type: ignore[no-untyped-def]
        global_chunk = await insert_chunk(
            admin_engine,
            tenant_id=None,
            document_id=uuid4(),
            text_value="world geography reference",
        )
        retriever = need("retrieval.VectorRetriever")(
            embedder=embedder, session_factory=async_sessionmaker(app_engines())
        )
        hits = await retriever.search("world geography reference", tenant_id=seed.tenant_b, k=3)
        assert global_chunk in {hit.chunk_id for hit in hits}

    async def test_an_empty_index_gives_no_hits(self, seed, app_engines, embedder) -> None:  # type: ignore[no-untyped-def]
        retriever = need("retrieval.VectorRetriever")(
            embedder=embedder, session_factory=async_sessionmaker(app_engines())
        )
        assert await retriever.search("anything", tenant_id=seed.tenant_a, k=5) == []

    async def test_a_selective_filter_still_returns_k_matches(
        self, seed, admin_engine, app_engines, embedder
    ) -> None:  # type: ignore[no-untyped-def]
        """Iterative index scans (pgvector >= 0.8): five matches hidden among many non-matches."""
        wanted = uuid4()
        for i in range(5):
            await insert_chunk(
                admin_engine, tenant_id=seed.tenant_a, document_id=wanted, text_value=f"match {i}"
            )
        for i in range(200):
            await insert_chunk(
                admin_engine, tenant_id=seed.tenant_a, document_id=uuid4(), text_value=f"noise {i}"
            )
        retriever = need("retrieval.VectorRetriever")(
            embedder=embedder, session_factory=async_sessionmaker(app_engines())
        )
        hits = await retriever.search(
            "match", tenant_id=seed.tenant_a, k=5, filters={"document_id": str(wanted)}
        )
        assert len(hits) == 5

    async def test_a_query_of_the_wrong_dimension_is_an_error(
        self, seed, admin_engine, app_engines
    ) -> None:  # type: ignore[no-untyped-def]
        # pgvector compares dimensions only when it meets a row, so the tenant needs at least one chunk
        await insert_chunk(
            admin_engine, tenant_id=seed.tenant_a, document_id=uuid4(), text_value="a stored chunk"
        )
        wrong = FakeEmbeddingProvider(dimension=8)
        retriever = need("retrieval.VectorRetriever")(
            embedder=wrong, session_factory=async_sessionmaker(app_engines())
        )
        with pytest.raises(Exception):  # noqa: B017 - the database rejects the vector dimension
            await retriever.search("x", tenant_id=seed.tenant_a, k=1)


class TestKeywordRetrieval:
    async def test_an_exact_term_is_found(self, seed, admin_engine, app_engines) -> None:  # type: ignore[no-untyped-def]
        target = await insert_chunk(
            admin_engine,
            tenant_id=seed.tenant_a,
            document_id=uuid4(),
            text_value="the zanzibar tariff",
        )
        retriever = need("retrieval.KeywordRetriever")(
            session_factory=async_sessionmaker(app_engines()), backend="fts"
        )
        hits = await retriever.search("zanzibar", tenant_id=seed.tenant_a, k=5)
        assert target in {hit.chunk_id for hit in hits}

    async def test_a_minus_operator_excludes_a_term(self, seed, admin_engine, app_engines) -> None:  # type: ignore[no-untyped-def]
        keep = await insert_chunk(
            admin_engine,
            tenant_id=seed.tenant_a,
            document_id=uuid4(),
            text_value="invoice schedule",
        )
        drop = await insert_chunk(
            admin_engine,
            tenant_id=seed.tenant_a,
            document_id=uuid4(),
            text_value="invoice refund policy",
        )
        retriever = need("retrieval.KeywordRetriever")(
            session_factory=async_sessionmaker(app_engines()), backend="fts"
        )
        ids = {
            hit.chunk_id
            for hit in await retriever.search("invoice -refund", tenant_id=seed.tenant_a, k=5)
        }
        assert keep in ids and drop not in ids

    async def test_sql_injection_text_is_inert(self, seed, admin_engine, app_engines) -> None:  # type: ignore[no-untyped-def]
        await insert_chunk(
            admin_engine, tenant_id=seed.tenant_a, document_id=uuid4(), text_value="ordinary text"
        )
        retriever = need("retrieval.KeywordRetriever")(
            session_factory=async_sessionmaker(app_engines()), backend="fts"
        )
        table = need("knowledge.ChunkModel").__table__.name
        hostile = "'; DROP TABLE " + table + "; --"
        assert isinstance(await retriever.search(hostile, tenant_id=seed.tenant_a, k=5), list)
        async with admin_engine.connect() as conn:
            exists = (
                await conn.execute(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": table})
            ).scalar_one()
        assert exists, "the injection string must never execute"

    async def test_another_tenant_never_sees_the_term(
        self, seed, admin_engine, app_engines
    ) -> None:  # type: ignore[no-untyped-def]
        await insert_chunk(
            admin_engine,
            tenant_id=seed.tenant_a,
            document_id=uuid4(),
            text_value="uniqueterm omega",
        )
        retriever = need("retrieval.KeywordRetriever")(
            session_factory=async_sessionmaker(app_engines()), backend="fts"
        )
        assert all(
            "omega" not in hit.text
            for hit in await retriever.search("omega", tenant_id=seed.tenant_b, k=5)
        )
