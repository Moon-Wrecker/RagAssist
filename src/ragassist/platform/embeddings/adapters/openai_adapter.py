"""OpenAI Dense Embedding Adapter."""

import asyncio
from typing import Any
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
import structlog

from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.shared.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)


class OpenAIEmbeddingAdapter(EmbeddingProvider):
    """Adapter for OpenAI dense embeddings via langchain-openai."""

    def __init__(
        self,
        model_name: str | None = None,
        dimension: int | None = None,
        batch_size: int | None = None,
        timeout: float = 15.0,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._model_name = model_name or self.settings.EMBEDDING_MODEL
        self._dimension = dimension or self.settings.EMBEDDING_DIMENSION
        self._batch_size = batch_size or self.settings.EMBEDDING_BATCH_SIZE
        self._timeout = timeout

        extra_kwargs: dict[str, Any] = {}
        if self._model_name.startswith("text-embedding-3"):
            extra_kwargs["dimensions"] = self._dimension

        api_key = self.settings.OPENAI_API_KEY
        if not api_key:
            logger.warning("openai_embeddings.no_api_key", model=self._model_name)

        self._client = OpenAIEmbeddings(
            model=self._model_name,
            api_key=api_key or "dummy-key-for-testing",
            timeout=self._timeout,
            **extra_kwargs,
        )

    @property
    def name(self) -> str:
        return "openai"

    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            batch_vectors = await asyncio.wait_for(
                self._client.aembed_documents(batch),
                timeout=self._timeout,
            )
            all_embeddings.extend(batch_vectors)
        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.wait_for(
            self._client.aembed_query(text),
            timeout=self._timeout,
        )

    def as_langchain_embeddings(self) -> Embeddings:
        return self._client
