"""The worker reads the object the document row names, inside the job tenant's prefix, not whatever a message says."""

from __future__ import annotations

from data.samples import MARKDOWN_SAMPLE
from support.knowledge_builders import Tenant, make_chunker, make_message, seed_queued_job
from support.specs import need


def worker_for(documents, store, embedder, counter):  # type: ignore[no-untyped-def]
    return need("knowledge.ProcessIngestionJob")(
        documents=documents,
        store=store,
        parsers={"text/markdown": need("knowledge.parser.markdown")()},
        chunker=make_chunker("knowledge.chunker.hybrid", counter),
        embedder=embedder,
        max_retries=3,
    )


async def test_a_forged_object_key_in_the_message_is_ignored(
    documents, store, embedder, counter, tenant: Tenant
) -> None:  # type: ignore[no-untyped-def]
    job = await seed_queued_job(documents, tenant, store, MARKDOWN_SAMPLE)
    foreign_key = "tenants/00000000-0000-0000-0000-00000000dead/documents/x/secret.md"
    await store.put_object(
        foreign_key, b"# Other tenant\n\nconfidential payroll data", content_type="text/markdown"
    )
    body = make_message(
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        object_key=foreign_key,
        document_id=job.document_id,
    )

    await worker_for(documents, store, embedder, counter).handle(body)

    texts = " ".join(
        str(getattr(c, "text", c)) for c in await documents.chunks_for(job.document_id)
    )
    assert "confidential payroll" not in texts


async def test_a_document_row_pointing_outside_the_tenant_prefix_fails_the_job(
    documents, store, embedder, counter, tenant: Tenant
) -> None:  # type: ignore[no-untyped-def]
    job = await seed_queued_job(documents, tenant, store, MARKDOWN_SAMPLE)
    doc = await documents.get_document(job.document_id)
    foreign_key = "tenants/00000000-0000-0000-0000-00000000dead/documents/x/secret.md"
    await store.put_object(
        foreign_key, b"# Other tenant\n\nconfidential payroll data", content_type="text/markdown"
    )
    for attr in ("s3_key", "object_key"):
        if hasattr(doc, attr):
            object.__setattr__(doc, attr, foreign_key)
    body = make_message(
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        object_key=foreign_key,
        document_id=job.document_id,
    )

    await worker_for(documents, store, embedder, counter).handle(body)

    assert await documents.chunks_for(job.document_id) == []
    assert "outside the tenant" in (documents.jobs[job.job_id].error_message or "")
