"""OpenAI Dense Embedding Adapter."""

import asyncio
import os
from typing import Any

import structlog
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.shared.config.settings import Settings, UNCONFIGURED_KEY, get_settings

logger = structlog.get_logger(__name__)


class OpenAIEmbeddingAdapter(EmbeddingProvider):
    """Adapter for OpenAI dense embeddings via langchain-openai."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        dimension: int | None = None,
        batch_size: int | None = None,
        timeout: float | None = None,
        settings: Settings | None = None,
        **kwargs: Any,
    ) -> None:
        self.settings = settings or get_settings()
        self._base_url = (
            base_url
            or kwargs.get("base_url")
            or getattr(self.settings, "OPENAI_BASE_URL", "")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
        )
        self._model_name = model_name or self.settings.EMBEDDING_MODEL
        self._dimension = dimension or self.settings.EMBEDDING_DIMENSION
        self._batch_size = batch_size or self.settings.EMBEDDING_BATCH_SIZE
        self._timeout = timeout if timeout is not None else self.settings.EMBEDDING_TIMEOUT_SECONDS

        extra_kwargs: dict[str, Any] = {}
        if self._model_name.startswith("text-embedding-3"):
            extra_kwargs["dimensions"] = self._dimension

        api_key = self.settings.OPENAI_API_KEY
        if not api_key:
            logger.warning("openai_embeddings.no_api_key", model=self._model_name)

        client_kwargs: dict[str, Any] = {
            "model": self._model_name,
            "api_key": api_key or UNCONFIGURED_KEY,
            "timeout": self._timeout,
            "check_embedding_ctx_length": False,
            **extra_kwargs,
        }
        if self._base_url:
            client_kwargs["base_url"] = self._base_url

        self._client = OpenAIEmbeddings(**client_kwargs)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        """The configured model; part of the embedding cache key (a new model must never reuse old vectors)."""
        return str(self._model_name)

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
