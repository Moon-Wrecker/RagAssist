"""Fixtures shared by the embedding tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from support.fake_openai_server import FakeOpenAIServer


@pytest.fixture
def embedding_server() -> Iterator[FakeOpenAIServer]:
    """A real loopback OpenAI-compatible server (the OpenAI SDK cannot be mocked with respx)."""
    server = FakeOpenAIServer(default_dimension=8).start()
    try:
        yield server
    finally:
        server.stop()
