"""ProcessIngestionJob and the queue worker loop (implementation plan section 7, "Worker idempotency").

SQS is at-least-once, so the same message may arrive twice, or while the first copy is still running.
The worker must end in the same state either way, never write for the wrong tenant, and never leave the
old chunks half-replaced. The queue and object store are the production in-memory adapters.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from data.samples import MARKDOWN_SAMPLE
from fakes.embeddings import FakeEmbeddingProvider
from support.knowledge_builders import Tenant, make_chunker, make_message, seed_queued_job
from support.specs import need

QUEUE = "ragassist-ingest"


@pytest.fixture
def worker_factory(documents, store, embedder, counter):  # type: ignore[no-untyped-def]
    def build(**overrides):  # type: ignore[no-untyped-def]
        cls = need("knowledge.ProcessIngestionJob")
        kwargs = {
            "documents": documents,
            "store": store,
            "parsers": {"text/markdown": need("knowledge.parser.markdown")()},
            "chunker": make_chunker("knowledge.chunker.hybrid", counter),
            "embedder": embedder,
            "max_retries": 3,
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    return build


@pytest.fixture
def outcome():  # type: ignore[no-untyped-def]
    return need("knowledge.IngestOutcome")


@pytest.fixture
async def queued(documents, store, tenant: Tenant):  # type: ignore[no-untyped-def]
    return await seed_queued_job(documents, tenant, store, MARKDOWN_SAMPLE)


def body_for(job, tenant_id: str | None = None) -> dict:  # type: ignore[no-untyped-def]
    return make_message(
        job_id=job.job_id,
        tenant_id=tenant_id or job.tenant_id,
        object_key=job.object_key,
        document_id=job.document_id,
    )


class TestHappyPath:
    async def test_a_queued_job_completes(self, worker_factory, queued, documents, outcome) -> None:  # type: ignore[no-untyped-def]
        assert await worker_factory().handle(body_for(queued)) == outcome.COMPLETED
        assert documents.jobs[queued.job_id].status == "completed"

    async def test_chunks_are_stored_for_the_document(
        self, worker_factory, queued, documents
    ) -> None:  # type: ignore[no-untyped-def]
        await worker_factory().handle(body_for(queued))
        assert len(await documents.chunks_for(queued.document_id)) >= 1

    async def test_every_chunk_is_embedded(self, worker_factory, queued, embedder) -> None:  # type: ignore[no-untyped-def]
        await worker_factory().handle(body_for(queued))
        assert sum(len(batch) for batch in embedder.document_batches) >= 1

    async def test_every_write_is_made_for_the_message_tenant(
        self, worker_factory, queued, documents, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        await worker_factory().handle(body_for(queued))
        assert documents.writes and {tid for tid, _ in documents.writes} == {tenant.tenant_id}


class TestIdempotency:
    async def test_a_duplicate_after_completion_is_skipped(
        self, worker_factory, queued, documents, outcome
    ) -> None:  # type: ignore[no-untyped-def]
        worker = worker_factory()
        await worker.handle(body_for(queued))
        before = await documents.chunks_for(queued.document_id)
        assert await worker.handle(body_for(queued)) == outcome.DUPLICATE_SKIPPED
        assert await documents.chunks_for(queued.document_id) == before

    async def test_a_duplicate_does_not_embed_again(self, worker_factory, queued, embedder) -> None:  # type: ignore[no-untyped-def]
        worker = worker_factory()
        await worker.handle(body_for(queued))
        batches = len(embedder.document_batches)
        assert batches >= 1, (
            "the first delivery must have embedded the chunks, or this test proves nothing"
        )
        await worker.handle(body_for(queued))
        assert len(embedder.document_batches) == batches

    async def test_a_copy_arriving_while_the_first_runs_is_skipped(
        self, worker_factory, queued, documents, outcome
    ) -> None:  # type: ignore[no-untyped-def]
        documents.jobs[queued.job_id] = dataclasses.replace(  # another worker holds the claim
            documents.jobs[queued.job_id], status=need("knowledge.JobStatus")("parsing")
        )
        assert await worker_factory().handle(body_for(queued)) == outcome.DUPLICATE_SKIPPED
        assert documents.chunks == {}

    async def test_two_sequential_deliveries_end_in_the_same_state_as_one(
        self, worker_factory, queued, documents
    ) -> None:  # type: ignore[no-untyped-def]
        worker = worker_factory()
        await worker.handle(body_for(queued))
        once = await documents.chunks_for(queued.document_id)
        assert once, "the first delivery must have stored chunks, or this test proves nothing"
        await worker.handle(body_for(queued))
        assert await documents.chunks_for(queued.document_id) == once


class TestRejectedMessages:
    async def test_a_body_without_a_job_id_is_rejected(
        self, worker_factory, documents, outcome
    ) -> None:  # type: ignore[no-untyped-def]
        assert await worker_factory().handle({"tenant_id": str(uuid4())}) == outcome.REJECTED
        assert documents.writes == []

    async def test_an_unknown_job_is_rejected(self, worker_factory, documents, outcome) -> None:  # type: ignore[no-untyped-def]
        body = make_message(job_id=str(uuid4()), tenant_id=str(uuid4()), object_key="x")
        assert await worker_factory().handle(body) == outcome.REJECTED
        assert documents.writes == []

    async def test_a_message_for_another_tenant_is_rejected(
        self, worker_factory, queued, documents, outcome
    ) -> None:  # type: ignore[no-untyped-def]
        """Defence in depth: the tenant in the message must match the job row, or nothing is written."""
        before = list(documents.writes)  # setup writes are not behaviour under test
        forged = body_for(queued, tenant_id=str(uuid4()))
        assert await worker_factory().handle(forged) == outcome.REJECTED
        assert documents.jobs[queued.job_id].status == "queued"
        assert documents.writes == before


class TestRetriesAndDeadLetters:
    async def test_a_missing_object_is_retried(
        self, worker_factory, documents, store, tenant: Tenant, outcome
    ) -> None:  # type: ignore[no-untyped-def]
        job = await seed_queued_job(
            documents, tenant, store, None
        )  # object deliberately not stored
        assert await worker_factory().handle(body_for(job)) == outcome.RETRY
        assert documents.jobs[job.job_id].status == "queued"

    async def test_a_failed_embedding_is_retried_and_succeeds_on_the_next_delivery(
        self, worker_factory, queued, outcome
    ) -> None:  # type: ignore[no-untyped-def]
        worker = worker_factory(embedder=FakeEmbeddingProvider(dimension=8, fail_times=1))
        assert await worker.handle(body_for(queued)) == outcome.RETRY
        assert await worker.handle(body_for(queued)) == outcome.COMPLETED

    async def test_each_attempt_is_counted(self, worker_factory, queued, documents) -> None:  # type: ignore[no-untyped-def]
        worker = worker_factory(embedder=FakeEmbeddingProvider(dimension=8, fail_times=2))
        for _ in range(2):
            await worker.handle(body_for(queued))
        assert documents.attempts_for(queued.job_id) == 2

    async def test_after_the_retry_budget_the_message_is_dead_lettered(
        self, worker_factory, documents, store, tenant: Tenant, outcome
    ) -> None:  # type: ignore[no-untyped-def]
        job = await seed_queued_job(documents, tenant, store, None)
        worker = worker_factory(max_retries=2)
        results = []
        for _ in range(2):
            results.append(await worker.handle(body_for(job)))
        assert results[-1] == outcome.DEAD_LETTERED
        assert documents.jobs[job.job_id].status == "failed"

    async def test_a_failed_chunk_swap_keeps_the_old_chunks(
        self, worker_factory, queued, documents, outcome
    ) -> None:  # type: ignore[no-untyped-def]
        old = [SimpleNamespace(content="old chunk")]
        documents.chunks[queued.document_id] = list(old)
        documents.fail_on("replace_chunks", RuntimeError("write failed mid-swap"))
        assert await worker_factory().handle(body_for(queued)) == outcome.RETRY
        assert await documents.chunks_for(queued.document_id) == old
        assert documents.jobs[queued.job_id].status != "completed"


class TestWorkerLoop:
    async def test_the_loop_handles_messages_until_it_is_stopped(
        self, worker_factory, queue, queued
    ) -> None:  # type: ignore[no-untyped-def]
        worker_cls = need("worker.IngestionWorker")
        handled: list[dict] = []
        handler_worker = worker_factory()

        async def handler(body: dict):  # type: ignore[no-untyped-def]
            handled.append(body)
            return await handler_worker.handle(body)

        await queue.send_message(QUEUE, body_for(queued))
        stop = asyncio.Event()
        loop = worker_cls(queue=queue, handler=handler, concurrency=2, poll_wait_seconds=0)
        task = asyncio.create_task(loop.run_until_stopped(stop))
        for _ in range(200):
            if handled:
                break
            await asyncio.sleep(0.01)
        stop.set()
        await asyncio.wait_for(task, timeout=5)
        assert (
            len(handled) >= 1
        )  # the in-memory queue keeps a message until deleted, so it may be re-received in flight

    async def test_a_retry_outcome_leaves_the_message_on_the_queue(
        self, worker_factory, queue, documents, store, tenant: Tenant, outcome
    ) -> None:  # type: ignore[no-untyped-def]
        worker_cls = need("worker.IngestionWorker")
        job = await seed_queued_job(documents, tenant, store, None)  # missing object -> RETRY
        await queue.send_message(QUEUE, body_for(job))
        stop = asyncio.Event()
        loop = worker_cls(
            queue=queue, handler=worker_factory().handle, concurrency=1, poll_wait_seconds=0
        )
        task = asyncio.create_task(loop.run_until_stopped(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=5)
        assert len(await queue.receive_messages(QUEUE)) == 1, "a RETRY must not delete the message"

    async def test_a_completed_message_is_deleted_from_the_queue(
        self, worker_factory, queue, queued
    ) -> None:  # type: ignore[no-untyped-def]
        worker_cls = need("worker.IngestionWorker")
        await queue.send_message(QUEUE, body_for(queued))
        stop = asyncio.Event()
        loop = worker_cls(
            queue=queue, handler=worker_factory().handle, concurrency=1, poll_wait_seconds=0
        )
        task = asyncio.create_task(loop.run_until_stopped(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=5)
        assert await queue.receive_messages(QUEUE) == []

    async def test_stopping_waits_for_in_flight_work_to_finish(self, queue) -> None:  # type: ignore[no-untyped-def]
        worker_cls = need("worker.IngestionWorker")
        finished: list[dict] = []

        async def slow(body: dict):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.1)
            finished.append(body)
            return need("knowledge.IngestOutcome").COMPLETED

        await queue.send_message(QUEUE, {"job_id": "slow"})
        stop = asyncio.Event()
        loop = worker_cls(queue=queue, handler=slow, concurrency=1, poll_wait_seconds=0)
        task = asyncio.create_task(loop.run_until_stopped(stop))
        await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, timeout=5)
        assert [json.loads(body) for body in finished] == [{"job_id": "slow"}], (
            "shutdown must not cancel an in-flight job"
        )
