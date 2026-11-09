"""Contract for the ``MessageQueue`` port (SQS in production; the in-memory adapter in unit tests).

The port: ``send_message(queue_name, message_body: dict, delay_seconds=0) -> str``,
``receive_messages(queue_name, max_messages=10, wait_time_seconds=10) -> list[dict]`` (each with
``message_id``, ``receipt_handle`` and ``body``), and ``delete_message(queue_name, receipt_handle) -> bool``.

Behaviour that is specific to one adapter (SQS visibility timeouts and dead-letter redrive; the
in-memory adapter's peek semantics) is asserted in that adapter's own test module, not here.
"""

from __future__ import annotations

import pytest

QUEUE = "ragassist-ingest"
OTHER_QUEUE = "ragassist-other"


class MessageQueueContract:
    @pytest.fixture
    def queue(self):  # type: ignore[no-untyped-def]  # pragma: no cover - overridden
        raise NotImplementedError

    async def test_send_returns_an_identifier(self, queue) -> None:  # type: ignore[no-untyped-def]
        message_id = await queue.send_message(QUEUE, {"job_id": "j1"})
        assert isinstance(message_id, str) and message_id

    async def test_receive_on_an_empty_queue_returns_nothing(self, queue) -> None:  # type: ignore[no-untyped-def]
        assert await queue.receive_messages(QUEUE, max_messages=5) == []

    async def test_a_sent_dict_body_is_delivered_unchanged(self, queue) -> None:  # type: ignore[no-untyped-def]
        body = {"job_id": "j1", "tenant_id": "t1", "note": "ünïcode 🚀", "nested": {"n": [1, 2]}}
        await queue.send_message(QUEUE, body)
        (message,) = await queue.receive_messages(QUEUE)
        assert message["body"] == body

    async def test_each_received_message_carries_its_identifiers(self, queue) -> None:  # type: ignore[no-untyped-def]
        sent = await queue.send_message(QUEUE, {"n": 1})
        (message,) = await queue.receive_messages(QUEUE)
        assert message["message_id"] == sent
        assert message["receipt_handle"]

    async def test_a_large_body_up_to_100_kib_is_delivered(self, queue) -> None:  # type: ignore[no-untyped-def]
        body = {"blob": "x" * (100 * 1024)}
        await queue.send_message(QUEUE, body)
        (message,) = await queue.receive_messages(QUEUE)
        assert message["body"] == body

    async def test_receive_honours_max_messages(self, queue) -> None:  # type: ignore[no-untyped-def]
        for i in range(3):
            await queue.send_message(QUEUE, {"i": i})
        assert len(await queue.receive_messages(QUEUE, max_messages=2)) == 2

    async def test_a_deleted_message_is_not_received_again(self, queue) -> None:  # type: ignore[no-untyped-def]
        await queue.send_message(QUEUE, {"done": True})
        (message,) = await queue.receive_messages(QUEUE)
        assert await queue.delete_message(QUEUE, message["receipt_handle"]) is True
        assert await queue.receive_messages(QUEUE) == []

    async def test_deleting_with_an_unknown_receipt_does_not_raise(self, queue) -> None:  # type: ignore[no-untyped-def]
        await queue.send_message(QUEUE, {"x": 1})
        await queue.delete_message(QUEUE, "not-a-real-receipt")  # must not raise

    async def test_queues_are_isolated_by_name(self, queue) -> None:  # type: ignore[no-untyped-def]
        await queue.send_message(QUEUE, {"where": "ingest"})
        assert await queue.receive_messages(OTHER_QUEUE) == []
        (message,) = await queue.receive_messages(QUEUE)
        assert message["body"] == {"where": "ingest"}

    async def test_bodies_are_json_serialisable_dicts(self, queue) -> None:  # type: ignore[no-untyped-def]
        await queue.send_message(QUEUE, {"ok": True, "count": 3, "tags": ["a", "b"]})
        (message,) = await queue.receive_messages(QUEUE)
        assert isinstance(message["body"], dict)
