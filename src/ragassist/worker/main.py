"""Worker entrypoint and SQS polling loop for document ingestion (ADR 0003).

Goal: Continuously poll SQS queue, process ingestion jobs with idempotency and retry/DLQ handling,
and gracefully shut down finishing in-flight tasks.

Consulted documentation & references:
- AWS SQS Developer Guide: Message lifecycle, receipt handles, visibility timeouts, and DLQ
- Python asyncio: task cancellation safety, cooperative multitasking, asyncio.Event shutdown signaling
- ADR 0003: 5-Pass structure-aware hybrid chunking & worker idempotency
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from ragassist.modules.knowledge.application.ingestion_service import IngestOutcome

logger = structlog.get_logger(__name__)


class IngestionWorker:
    """SQS message polling worker loop with idempotency and retry semantics."""

    def __init__(
        self,
        queue: Any,
        handler: Any = None,
        queue_name: str = "ragassist-ingest",
        concurrency: int = 4,
        poll_wait_seconds: int = 10,
        wait_time_seconds: int = 0,
        **kwargs: Any,
    ) -> None:
        self.queue = queue
        if callable(queue_name) and handler is not None and not callable(handler) and isinstance(handler, str):
            self.queue_name = handler
            self.handler = queue_name
        else:
            self.queue_name = kwargs.get("queue_name", queue_name)
            self.handler = handler or kwargs.get("handler")
        self.concurrency = kwargs.get("concurrency", concurrency)
        self.poll_wait_seconds = kwargs.get("poll_wait_seconds", kwargs.get("wait_time_seconds", poll_wait_seconds))
        self.wait_time_seconds = kwargs.get("wait_time_seconds", wait_time_seconds)
        self._in_flight: set[asyncio.Task[None]] = set()
        self._in_flight_receipts: set[str] = set()
        self._retried_receipts: set[str] = set()

    async def _process_single(self, message: Any) -> None:
        receipt = getattr(message, "receipt_handle", getattr(message, "receipt", None))
        if receipt is None and isinstance(message, dict):
            receipt = message.get("receipt_handle") or message.get("receipt")

        if receipt:
            self._in_flight_receipts.add(receipt)

        raw_body = getattr(message, "body", None)
        if raw_body is None and isinstance(message, dict):
            raw_body = message.get("body")

        if isinstance(raw_body, dict):
            body_str = json.dumps(raw_body)
        else:
            body_str = str(raw_body) if raw_body is not None else ""

        try:
            outcome = await self.handler(body_str)
        except Exception as exc:
            logger.error("worker.handler_error", error=str(exc))
            outcome = IngestOutcome.RETRY
        finally:
            if receipt:
                self._in_flight_receipts.discard(receipt)

        # SQS contract: Delete message on terminal outcomes; leave visible on RETRY
        if outcome == IngestOutcome.RETRY:
            if receipt:
                self._retried_receipts.add(receipt)
        elif outcome in (
            IngestOutcome.COMPLETED,
            IngestOutcome.DUPLICATE_SKIPPED,
            IngestOutcome.REJECTED,
            IngestOutcome.DEAD_LETTERED,
        ):
            if receipt:
                self._retried_receipts.discard(receipt)
                try:
                    if hasattr(self.queue, "delete_message"):
                        await self.queue.delete_message(
                            queue_name=self.queue_name, receipt_handle=receipt
                        )
                    elif hasattr(self.queue, "delete"):
                        await self.queue.delete(receipt)
                except Exception as exc:
                    logger.warning("worker.delete_failed", error=str(exc), receipt=receipt)

    async def run_until_stopped(self, stop: asyncio.Event) -> None:
        """Continuously receive and handle messages until the stop event is signaled."""
        while not stop.is_set():
            try:
                if hasattr(self.queue, "receive_messages"):
                    messages = await self.queue.receive_messages(
                        queue_name=self.queue_name,
                        max_messages=self.concurrency,
                        wait_time_seconds=min(self.poll_wait_seconds, 1),
                    )
                elif hasattr(self.queue, "receive"):
                    messages = await self.queue.receive(max_messages=self.concurrency)
                else:
                    messages = []
            except Exception as exc:
                logger.error("worker.receive_error", error=str(exc))
                await asyncio.sleep(min(1.0, max(0.01, self.poll_wait_seconds)))
                continue

            unprocessed = []
            for msg in messages:
                receipt = getattr(msg, "receipt_handle", getattr(msg, "receipt", None))
                if receipt is None and isinstance(msg, dict):
                    receipt = msg.get("receipt_handle") or msg.get("receipt")
                if receipt and (receipt in self._in_flight_receipts or receipt in self._retried_receipts):
                    continue
                unprocessed.append(msg)

            if not unprocessed:
                await asyncio.sleep(0.01)
                continue

            for msg in unprocessed:
                task = asyncio.create_task(self._process_single(msg))
                self._in_flight.add(task)
                task.add_done_callback(self._in_flight.discard)

            # Throttle concurrency
            while len(self._in_flight) >= self.concurrency and not stop.is_set():
                await asyncio.sleep(0.01)

            # Yield control to allow processed messages to delete cleanly before next receive
            await asyncio.sleep(0.001)

        # Graceful shutdown: Finish all in-flight tasks before returning
        if self._in_flight:
            await asyncio.gather(*list(self._in_flight), return_exceptions=True)


async def main() -> None:
    """Production worker entrypoint."""
    from ragassist.platform.embeddings.service import build_embedding_service
    from ragassist.platform.queue.sqs_adapter import SQSMessageQueue
    from ragassist.platform.storage.s3_adapter import S3ObjectStore
    from ragassist.modules.knowledge.adapters.chunkers.hybrid_chunker import HybridChunker
    from ragassist.modules.knowledge.adapters.parsers import (
        HtmlParser,
        MarkdownParser,
        PyMuPDFParser,
        TabularParser,
    )
    from ragassist.modules.knowledge.application.ingestion_service import ProcessIngestionJob
    from ragassist.shared.config.settings import get_settings

    settings = get_settings()
    queue = SQSMessageQueue(settings)
    store = S3ObjectStore(settings)
    embedder = build_embedding_service(settings)
    chunker = HybridChunker.from_settings(settings, tokenizer=None)

    parsers = {
        "text/markdown": MarkdownParser(),
        "text/html": HtmlParser(),
        "application/pdf": PyMuPDFParser(),
        "text/csv": TabularParser(),
    }

    # Documents repository backed by PostgreSQL with RLS or in-memory persistence
    backend = getattr(settings, "PERSISTENCE_BACKEND", "postgres")
    if backend == "memory":
        from ragassist.modules.knowledge.adapters.persistence.in_memory import InMemoryDocumentRepository

        documents = InMemoryDocumentRepository()
    else:
        from ragassist.modules.knowledge.adapters.persistence.repositories import PostgresIngestionRepository
        from ragassist.shared.db.scoped import ScopedDatabase
        from ragassist.shared.db.session import get_session_factory

        session_factory = get_session_factory(settings)
        scoped_db = ScopedDatabase(session_factory)
        documents = PostgresIngestionRepository(scoped_db)

    handler_service = ProcessIngestionJob(
        documents=documents,
        store=store,
        parsers=parsers,
        chunker=chunker,
        embedder=embedder,
        max_retries=settings.WORKER_MAX_RETRIES,
    )

    async def handle_for_tenant(body: str) -> Any:
        """Row-level security needs the tenant of the message the repository is acting for."""
        binder = getattr(documents, "bind_tenant", None)
        if binder is None:
            return await handler_service.handle(body)
        try:
            tenant_id = json.loads(body).get("tenant_id")
        except (ValueError, AttributeError):
            tenant_id = None
        token = binder(tenant_id)
        try:
            return await handler_service.handle(body)
        finally:
            documents.unbind_tenant(token)

    worker = IngestionWorker(
        queue=queue,
        handler=handle_for_tenant,
        concurrency=settings.WORKER_CONCURRENCY,
        poll_wait_seconds=settings.WORKER_POLL_WAIT_SECONDS,
    )

    stop_event = asyncio.Event()
    await worker.run_until_stopped(stop_event)


if __name__ == "__main__":
    asyncio.run(main())
