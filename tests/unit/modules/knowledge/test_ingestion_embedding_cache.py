"""Re-indexing an unchanged document makes no embedding call when the embedding cache is on (ADR 0015)."""

from __future__ import annotations

from data.samples import MARKDOWN_SAMPLE
from fakes.embeddings import FakeEmbeddingProvider
from support.knowledge_builders import Tenant, make_chunker, make_message, seed_queued_job
from support.settings import make_settings
from support.specs import need

from ragassist.platform.cache import build_cache_service
from ragassist.platform.cache.adapters.memory_adapter import InMemoryCache
from ragassist.platform.embeddings.service import EmbeddingService
from ragassist.shared.resilience import FallbackChain


async def index_once(documents, store, counter, tenant: Tenant, embedder):  # type: ignore[no-untyped-def]
    job = await seed_queued_job(documents, tenant, store, MARKDOWN_SAMPLE)
    worker = need("knowledge.ProcessIngestionJob")(
        documents=documents,
        store=store,
        parsers={"text/markdown": need("knowledge.parser.markdown")()},
        chunker=make_chunker("knowledge.chunker.hybrid", counter),
        embedder=embedder,
        max_retries=3,
    )
    outcome = await worker.handle(
        make_message(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            object_key=job.object_key,
            document_id=job.document_id,
        )
    )
    return str(outcome.value)


def embedding_service(provider: FakeEmbeddingProvider, *, enabled: bool) -> EmbeddingService:
    cfg = make_settings(CACHE_ENABLED=enabled)
    memory = InMemoryCache(max_entries=1000, max_value_bytes=65536)
    return EmbeddingService(
        FallbackChain(name="emb", members=[provider]),
        expected_dimension=8,
        cache=build_cache_service(cfg, memory if enabled else None),
    )


async def test_a_second_pass_over_identical_content_embeds_nothing(
    documents, store, counter, tenant: Tenant
) -> None:  # type: ignore[no-untyped-def]
    provider = FakeEmbeddingProvider(dimension=8)
    embedder = embedding_service(provider, enabled=True)

    assert await index_once(documents, store, counter, tenant, embedder) == "COMPLETED"
    first_pass_texts = sum(len(b) for b in provider.document_batches)
    assert first_pass_texts > 0

    assert await index_once(documents, store, counter, tenant, embedder) == "COMPLETED"
    assert (
        sum(len(b) for b in provider.document_batches) == first_pass_texts
    )  # nothing new was embedded


async def test_with_the_cache_off_every_pass_embeds_everything(
    documents, store, counter, tenant: Tenant
) -> None:  # type: ignore[no-untyped-def]
    provider = FakeEmbeddingProvider(dimension=8)
    embedder = embedding_service(provider, enabled=False)

    await index_once(documents, store, counter, tenant, embedder)
    one_pass = sum(len(b) for b in provider.document_batches)
    await index_once(documents, store, counter, tenant, embedder)
    assert sum(len(b) for b in provider.document_batches) == 2 * one_pass
