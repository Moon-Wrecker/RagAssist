"""Abstract contract suites: one per port, written once, run against every adapter.

Pattern (Liskov-style): the contract class declares the behaviour every implementation of a port
must show. Concrete test modules subclass it, provide the ``provider`` fixture, and get all the
tests for free. Names of contract classes do NOT start with ``Test`` so pytest never collects them
directly; only the subclasses do.
"""

from support.contracts.chat_provider import ChatModelProviderContract
from support.contracts.chunker import ChunkerContract
from support.contracts.decider import DeciderContract
from support.contracts.embedding_provider import EmbeddingProviderContract
from support.contracts.message_queue import MessageQueueContract
from support.contracts.object_store import ObjectStoreContract
from support.contracts.parser import ParserContract
from support.contracts.reranker import RerankerContract
from support.contracts.retriever import RetrieverContract

__all__ = [
    "ChatModelProviderContract",
    "ChunkerContract",
    "DeciderContract",
    "EmbeddingProviderContract",
    "MessageQueueContract",
    "ObjectStoreContract",
    "ParserContract",
    "RerankerContract",
    "RetrieverContract",
]
