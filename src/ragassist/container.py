"""Application composition root and dependency injection container.

Coordinates configuration, platform adapters (storage, queues, providers),
and domain application services across bounded contexts following Hexagonal Architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from ragassist.platform.queue.sqs_adapter import InMemoryMessageQueue, SQSMessageQueue
from ragassist.platform.storage.ports import MessageQueue, ObjectStore
from ragassist.platform.storage.s3_adapter import InMemoryObjectStore, S3ObjectStore
from ragassist.shared.config.settings import Settings, get_settings


@dataclass
class Container:
    """Application dependency container providing singleton and factory access to services."""

    settings: Settings = field(default_factory=get_settings)
    _object_store: ObjectStore | None = None
    _message_queue: MessageQueue | None = None

    @property
    def object_store(self) -> ObjectStore:
        """Resolve object store: S3 adapter in cloud/LocalStack mode, in-memory store in offline mode."""
        if self._object_store is None:
            if self.settings.USE_LOCALSTACK or self.settings.AWS_ACCESS_KEY_ID:
                try:
                    self._object_store = S3ObjectStore(settings=self.settings)
                except Exception:
                    self._object_store = InMemoryObjectStore()
            else:
                self._object_store = InMemoryObjectStore()
        return self._object_store

    @property
    def message_queue(self) -> MessageQueue:
        """Resolve message queue: SQS adapter in cloud/LocalStack mode, in-memory queue in offline mode."""
        if self._message_queue is None:
            if self.settings.USE_LOCALSTACK or self.settings.AWS_ACCESS_KEY_ID:
                try:
                    self._message_queue = SQSMessageQueue(settings=self.settings)
                except Exception:
                    self._message_queue = InMemoryMessageQueue()
            else:
                self._message_queue = InMemoryMessageQueue()
        return self._message_queue


@lru_cache(maxsize=1)
def get_container() -> Container:
    """Return the global application container singleton."""
    return Container()


container = get_container()
