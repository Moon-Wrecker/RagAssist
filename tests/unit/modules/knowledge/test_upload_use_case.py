"""UploadDocument (implementation plan sections 4 and 9): the storage key, the job row, the queue message,
and the rule that a failed step leaves no job row and no orphaned object behind.

The object store and the queue are the production in-memory adapters; failures are injected by
subclassing them, so the code under test is real.
"""

from __future__ import annotations

import pytest
from support.knowledge_builders import Tenant
from support.specs import need

QUEUE = "ragassist-ingest"


def failing_put_store(error: BaseException):  # type: ignore[no-untyped-def]
    base = need("storage.memory")

    class FailingPutStore(base):  # type: ignore[valid-type,misc]
        async def put_object(
            self, key, data, content_type="application/octet-stream", metadata=None
        ):  # type: ignore[no-untyped-def]
            raise error

    return FailingPutStore()


def failing_send_queue(error: BaseException):  # type: ignore[no-untyped-def]
    base = need("queue.memory")

    class FailingSendQueue(base):  # type: ignore[valid-type,misc]
        async def send_message(self, queue_name, message_body, delay_seconds=0):  # type: ignore[no-untyped-def]
            raise error

    return FailingSendQueue()


class TestHappyPath:
    async def test_the_object_is_stored_under_the_tenant_prefix(
        self, upload_factory, command_factory, store, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        result = await upload_factory().execute(command_factory(tenant))
        assert result.object_key.startswith(f"tenants/{tenant.tenant_id}/")
        assert await store.get_object(result.object_key) == b"# Guide\n\nHello."

    async def test_a_queued_job_row_is_created(
        self, upload_factory, command_factory, documents, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        result = await upload_factory().execute(command_factory(tenant))
        assert documents.jobs[result.job_id].status == "queued"

    async def test_one_message_is_sent_with_the_job_and_tenant(
        self, upload_factory, command_factory, queue, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        result = await upload_factory().execute(command_factory(tenant))
        (message,) = await queue.receive_messages(QUEUE, max_messages=10)
        assert message["body"]["job_id"] == result.job_id
        assert message["body"]["tenant_id"] == tenant.tenant_id
        assert message["body"]["object_key"] == result.object_key

    async def test_the_result_carries_identifiers(
        self, upload_factory, command_factory, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        result = await upload_factory().execute(command_factory(tenant))
        assert result.job_id and result.document_id and result.object_key

    async def test_each_upload_gets_its_own_job(
        self, upload_factory, command_factory, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        use_case = upload_factory()
        first = await use_case.execute(command_factory(tenant))
        second = await use_case.execute(command_factory(tenant))
        assert first.job_id != second.job_id and first.object_key != second.object_key

    async def test_the_object_holds_the_uploaded_bytes(
        self, upload_factory, command_factory, store, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        result = await upload_factory().execute(command_factory(tenant, content=b"exact bytes"))
        assert await store.get_object(result.object_key) == b"exact bytes"


class TestValidation:
    async def test_an_unsupported_mime_type_is_refused_before_anything_is_written(
        self,
        upload_factory,
        command_factory,
        store,
        documents,
        queue,
        tenant: Tenant,  # type: ignore[no-untyped-def]
    ) -> None:
        with pytest.raises(need("knowledge.UnsupportedMimeType")):
            await upload_factory().execute(command_factory(tenant, mime="application/x-msdownload"))
        assert documents.jobs == {} and await queue.receive_messages(QUEUE) == []

    async def test_an_oversized_file_is_refused_before_anything_is_written(
        self,
        upload_factory,
        command_factory,
        documents,
        queue,
        tenant: Tenant,  # type: ignore[no-untyped-def]
    ) -> None:
        with pytest.raises(need("knowledge.FileTooLarge")):
            await upload_factory(max_bytes=10).execute(command_factory(tenant, content=b"x" * 11))
        assert documents.jobs == {} and await queue.receive_messages(QUEUE) == []

    async def test_a_file_exactly_at_the_limit_is_accepted(
        self, upload_factory, command_factory, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        result = await upload_factory(max_bytes=10).execute(
            command_factory(tenant, content=b"x" * 10)
        )
        assert result.job_id

    async def test_path_traversal_in_the_filename_cannot_escape_the_tenant_prefix(
        self,
        upload_factory,
        command_factory,
        tenant: Tenant,  # type: ignore[no-untyped-def]
    ) -> None:
        result = await upload_factory().execute(
            command_factory(tenant, filename="../../other-tenant/secret.md")
        )
        segments = result.object_key.split("/")
        assert segments[:2] == ["tenants", tenant.tenant_id]
        assert ".." not in segments


class TestAtomicity:
    async def test_a_failed_object_write_leaves_no_job_row(
        self, upload_factory, command_factory, documents, queue, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(RuntimeError):
            await upload_factory(store=failing_put_store(RuntimeError("S3 down"))).execute(
                command_factory(tenant)
            )
        assert documents.jobs == {} and await queue.receive_messages(QUEUE) == []

    async def test_a_failed_queue_send_removes_the_job_and_the_object(
        self, upload_factory, command_factory, store, documents, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(RuntimeError):
            await upload_factory(queue=failing_send_queue(RuntimeError("SQS unavailable"))).execute(
                command_factory(tenant)
            )
        assert documents.jobs == {}, "no job row may survive a failed send"
        assert await _objects_under(store, tenant) == [], (
            "no orphaned object may survive a failed send"
        )

    async def test_a_failed_job_insert_removes_the_object(
        self, upload_factory, command_factory, store, documents, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        documents.fail_on("add_job", RuntimeError("db down"))
        with pytest.raises(RuntimeError):
            await upload_factory().execute(command_factory(tenant))
        assert await _objects_under(store, tenant) == []

    async def test_a_failed_upload_sends_no_message(
        self, upload_factory, command_factory, queue, tenant: Tenant
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(RuntimeError):
            await upload_factory(store=failing_put_store(RuntimeError("S3 down"))).execute(
                command_factory(tenant)
            )
        assert await queue.receive_messages(QUEUE) == []


async def _objects_under(store, tenant: Tenant) -> list[str]:  # type: ignore[no-untyped-def]
    """Keys under the tenant prefix. The in-memory adapter does not list keys, so the adapter's own
    record is read; the contract for real stores is a list operation that the port does not expose."""
    prefix = f"tenants/{tenant.tenant_id}/"
    return sorted(key for key in getattr(store, "_storage", {}) if key.startswith(prefix))
