"""The job row is returned by the API, so the failure reason it stores must not carry exception text."""

from __future__ import annotations

from data.samples import MARKDOWN_SAMPLE
from support.knowledge_builders import Tenant, make_chunker, make_message, seed_queued_job
from support.specs import need


class LeakyEmbedder:
    """Fails the way an HTTP client does: the exception text names the internal host."""

    def dimension(self) -> int:
        return 8

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("POST http://10.1.2.3:11434/v1/embeddings failed: connection refused")


async def test_the_stored_reason_names_the_stage_not_the_exception_text(
    documents, store, counter, tenant: Tenant
) -> None:  # type: ignore[no-untyped-def]
    job = await seed_queued_job(documents, tenant, store, MARKDOWN_SAMPLE)
    worker = need("knowledge.ProcessIngestionJob")(
        documents=documents,
        store=store,
        parsers={"text/markdown": need("knowledge.parser.markdown")()},
        chunker=make_chunker("knowledge.chunker.hybrid", counter),
        embedder=LeakyEmbedder(),
        max_retries=3,
    )
    body = make_message(
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        object_key=job.object_key,
        document_id=job.document_id,
    )

    await worker.handle(body)

    stored = documents.jobs[job.job_id].error_message
    assert stored == "embed failed (RuntimeError)"
    assert "10.1.2.3" not in stored
