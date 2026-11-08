"""Test doubles. Each fake implements a real port and is itself checked against that port's
contract suite (tests/selfcheck), so a fake can never silently drift from the contract."""

from fakes.chat_model import ScriptedChatModel
from fakes.embeddings import FakeEmbeddingProvider
from fakes.session import FakeAsyncSession
from fakes.vector_store import InMemoryVectorStore

__all__ = [
    "FakeAsyncSession",
    "FakeEmbeddingProvider",
    "InMemoryVectorStore",
    "ScriptedChatModel",
]
