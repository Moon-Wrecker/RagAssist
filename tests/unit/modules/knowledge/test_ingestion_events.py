"""The ingestion worker announces job and document changes (ids only) and never fails because of the announcement."""

from __future__ import annotations

from data.samples import MARKDOWN_SAMPLE
from fakes.embeddings import FakeEmbeddingProvider
from support.knowledge_builders import Tenant, make_chunker, make_message, seed_queued_job
from support.specs import need

from ragassist.platform.events import Event, InMemoryEventBus


async def run_job(
    documents, store, counter, tenant: Tenant, *, embedder, events, max_retries: int = 3
):  # type: ignore[no-untyped-def]
    job = await seed_queued_job(documents, tenant, store, MARKDOWN_SAMPLE)
    worker = need("knowledge.ProcessIngestionJob")(
        documents=documents,
        store=store,
        parsers={"text/markdown": need("knowledge.parser.markdown")()},
        chunker=make_chunker("knowledge.chunker.hybrid", counter),
        embedder=embedder,
        max_retries=max_retries,
        events=events,
    )
    body = make_message(
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        object_key=job.object_key,
        document_id=job.document_id,
    )
    outcome = await worker.handle(body)
    return job, outcome


def kinds(bus: InMemoryEventBus) -> list[str]:
    return [e.type for e in bus.published]


async def test_a_completed_job_announces_start_and_finish_with_ids_only(
    documents, store, counter, tenant: Tenant
) -> None:  # type: ignore[no-untyped-def]
    bus = InMemoryEventBus()
    job, _ = await run_job(
        documents, store, counter, tenant, embedder=FakeEmbeddingProvider(dimension=8), events=bus
    )

    assert kinds(bus) == ["job.updated", "document.changed", "job.updated", "document.changed"]
    for event in bus.published:
        assert event.tenant_id == str(job.tenant_id)
        assert set(event.data) <= {"job_id", "document_id"}
    assert dict(bus.published[0].data) == {
        "job_id": str(job.job_id),
        "document_id": str(job.document_id),
    }


async def test_a_failed_attempt_announces_the_state_change(
    documents, store, counter, tenant: Tenant
) -> None:  # type: ignore[no-untyped-def]
    bus = InMemoryEventBus()
    await run_job(
        documents,
        store,
        counter,
        tenant,
        embedder=FakeEmbeddingProvider(dimension=8, fail_times=1),
        events=bus,
    )
    assert kinds(bus).count("job.updated") == 2  # claimed, then back to queued for the retry


async def test_a_broken_event_channel_does_not_fail_the_job(
    documents, store, counter, tenant: Tenant
) -> None:  # type: ignore[no-untyped-def]
    class Broken:
        async def publish(self, event: Event) -> None:
            raise RuntimeError("database is down")

    _, outcome = await run_job(
        documents,
        store,
        counter,
        tenant,
        embedder=FakeEmbeddingProvider(dimension=8),
        events=Broken(),
    )
    assert str(outcome.value) == "COMPLETED"


async def test_without_a_publisher_nothing_changes(
    documents, store, counter, tenant: Tenant
) -> None:  # type: ignore[no-untyped-def]
    _, outcome = await run_job(
        documents, store, counter, tenant, embedder=FakeEmbeddingProvider(dimension=8), events=None
    )
    assert str(outcome.value) == "COMPLETED"
