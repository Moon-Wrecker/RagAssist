"""Abstract ports and contracts for Object Storage (S3) and Message Queues (SQS)."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ObjectStore(Protocol):
    """Protocol for interacting with object storage (S3/LocalStack)."""

    async def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream", metadata: dict[str, str] | None = None) -> str:
        """Store raw bytes in object storage and return the object URL/URI."""
        ...

    async def get_object(self, key: str) -> bytes:
        """Retrieve raw object bytes by key."""
        ...

    async def delete_object(self, key: str) -> bool:
        """Delete an object by key."""
        ...


@runtime_checkable
class MessageQueue(Protocol):
    """Protocol for asynchronous message queuing (SQS/LocalStack)."""

    async def send_message(self, queue_name: str, message_body: dict[str, Any], delay_seconds: int = 0) -> str:
        """Enqueue a JSON-serializable message and return message ID."""
        ...

    async def receive_messages(self, queue_name: str, max_messages: int = 10, wait_time_seconds: int = 10) -> list[dict[str, Any]]:
        """Receive a batch of messages from the queue."""
        ...

    async def delete_message(self, queue_name: str, receipt_handle: str) -> bool:
        """Acknowledge and delete a processed message from the queue."""
        ...

