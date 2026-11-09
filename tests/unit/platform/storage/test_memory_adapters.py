"""The production in-memory adapters, run against the storage and queue port contracts.

The in-memory adapters are real production code (no external services), so they are the default
implementation in unit tests. The S3 and SQS adapters run the same contracts against LocalStack in
tests/integration.
"""

from __future__ import annotations

import pytest
from support.contracts import MessageQueueContract, ObjectStoreContract
from support.specs import need


class TestInMemoryObjectStoreMeetsContract(ObjectStoreContract):
    @pytest.fixture
    def store(self):  # type: ignore[no-untyped-def]
        return need("storage.memory")()


class TestInMemoryMessageQueueMeetsContract(MessageQueueContract):
    @pytest.fixture
    def queue(self):  # type: ignore[no-untyped-def]
        return need("queue.memory")()


class TestInMemoryQueueSemantics:
    """Peek semantics are the in-memory adapter's own: a received message stays until it is deleted.
    SQS behaves differently (visibility timeouts), and that is tested against LocalStack."""

    async def test_an_unacknowledged_message_is_received_again(self) -> None:
        queue = need("queue.memory")()
        await queue.send_message("q", {"retry": True})
        first = await queue.receive_messages("q")
        second = await queue.receive_messages("q")
        assert first and second and first[0]["body"] == second[0]["body"]

    async def test_receiving_does_not_remove_the_message(self) -> None:
        queue = need("queue.memory")()
        await queue.send_message("q", {"keep": True})
        await queue.receive_messages("q")
        assert len(await queue.receive_messages("q")) == 1


class TestInMemoryObjectStoreSemantics:
    async def test_put_returns_a_mem_uri_for_the_key(self) -> None:
        store = need("storage.memory")()
        assert await store.put_object("a/b", b"x") == "mem://a/b"

    async def test_content_type_and_metadata_are_kept_with_the_object(self) -> None:
        store = need("storage.memory")()
        await store.put_object("m", b"x", content_type="text/plain", metadata={"k": "v"})
        stored = store._storage["m"]  # the adapter's own record; the port does not expose metadata
        assert stored[1] == "text/plain" and stored[2] == {"k": "v"}
