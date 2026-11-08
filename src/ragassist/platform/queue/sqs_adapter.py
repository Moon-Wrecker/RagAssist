"""SQS and in-memory message queue adapters."""

import asyncio
import json
from typing import Any
from uuid import uuid4
import aioboto3
from ragassist.platform.storage.ports import MessageQueue
from ragassist.shared.config.settings import Settings, get_settings


class SQSMessageQueue(MessageQueue):
    """Adapter for AWS SQS and LocalStack SQS."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = aioboto3.Session(
            aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY,
            region_name=self.settings.AWS_REGION,
        )
        self._queue_url_cache: dict[str, str] = {}

    def _get_client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self.settings.USE_LOCALSTACK and self.settings.LOCALSTACK_ENDPOINT:
            kwargs["endpoint_url"] = self.settings.LOCALSTACK_ENDPOINT
        return kwargs

    async def _get_queue_url(self, client: Any, queue_name: str) -> str:
        if queue_name not in self._queue_url_cache:
            resp = await client.get_queue_url(QueueName=queue_name)
            self._queue_url_cache[queue_name] = resp["QueueUrl"]
        return self._queue_url_cache[queue_name]

    async def send_message(self, queue_name: str, message_body: dict[str, Any], delay_seconds: int = 0) -> str:
        async with self.session.client("sqs", **self._get_client_kwargs()) as sqs:
            q_url = await self._get_queue_url(sqs, queue_name)
            resp = await sqs.send_message(
                QueueUrl=q_url,
                MessageBody=json.dumps(message_body),
                DelaySeconds=delay_seconds,
            )
            return resp.get("MessageId", str(uuid4()))

    async def receive_messages(self, queue_name: str, max_messages: int = 10, wait_time_seconds: int = 10) -> list[dict[str, Any]]:
        async with self.session.client("sqs", **self._get_client_kwargs()) as sqs:
            q_url = await self._get_queue_url(sqs, queue_name)
            resp = await sqs.receive_message(
                QueueUrl=q_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds,
            )
            messages = []
            for msg in resp.get("Messages", []):
                messages.append({
                    "message_id": msg["MessageId"],
                    "receipt_handle": msg["ReceiptHandle"],
                    "body": json.loads(msg["Body"]),
                })
            return messages

    async def delete_message(self, queue_name: str, receipt_handle: str) -> bool:
        async with self.session.client("sqs", **self._get_client_kwargs()) as sqs:
            q_url = await self._get_queue_url(sqs, queue_name)
            await sqs.delete_message(QueueUrl=q_url, ReceiptHandle=receipt_handle)
            return True


class InMemoryMessageQueue(MessageQueue):
    """In-memory queue for offline execution, integration tests, and local dev."""

    def __init__(self) -> None:
        self._queues: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}

    async def send_message(self, queue_name: str, message_body: dict[str, Any], delay_seconds: int = 0) -> str:
        msg_id = str(uuid4())
        handle = f"hnd_{uuid4()}"
        if queue_name not in self._queues:
            self._queues[queue_name] = []
        self._queues[queue_name].append((msg_id, handle, message_body))
        return msg_id

    async def receive_messages(self, queue_name: str, max_messages: int = 10, wait_time_seconds: int = 10) -> list[dict[str, Any]]:
        if queue_name not in self._queues or not self._queues[queue_name]:
            return []
        items = self._queues[queue_name][:max_messages]
        return [
            {"message_id": mid, "receipt_handle": hnd, "body": body}
            for mid, hnd, body in items
        ]

    async def delete_message(self, queue_name: str, receipt_handle: str) -> bool:
        if queue_name not in self._queues:
            return False
        self._queues[queue_name] = [
            item for item in self._queues[queue_name] if item[1] != receipt_handle
        ]
        return True

