"""OpenAI-Compatible Dense Embedding Adapter (Ollama, vLLM, LM Studio)."""

import asyncio
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
import structlog

from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.platform.embeddings.projector import DimensionProjector
from ragassist.shared.config.settings import Settings, UNCONFIGURED_KEY, get_settings

logger = structlog.get_logger(__name__)


class OpenAICompatibleEmbeddingAdapter(EmbeddingProvider):
    """Adapter for local or self-hosted OpenAI-compatible embedding servers."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        dimension: int | None = None,
        batch_size: int | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._base_url = base_url or self.settings.OPENAI_COMPATIBLE_BASE_URL
        self._model_name = model_name or self.settings.OPENAI_COMPATIBLE_EMBEDDING_MODEL
        self._dimension = dimension or self.settings.EMBEDDING_DIMENSION
        self._batch_size = batch_size or self.settings.EMBEDDING_BATCH_SIZE
        self._api_key = api_key or self.settings.OPENAI_COMPATIBLE_API_KEY or UNCONFIGURED_KEY
        self._timeout = timeout if timeout is not None else self.settings.EMBEDDING_TIMEOUT_SECONDS
        self._projector = DimensionProjector(target_dimension=self._dimension)

        self._client = OpenAIEmbeddings(
            base_url=self._base_url,
            model=self._model_name,
            api_key=self._api_key,
            timeout=self._timeout,
            check_embedding_ctx_length=False,  # Prevents tiktoken KeyError on local models
        )

    @property
    def name(self) -> str:
        return "openai_compatible"

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
            projected = self._projector.project_vectors(batch_vectors)
            all_embeddings.extend(projected)
        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        raw_vec = await asyncio.wait_for(
            self._client.aembed_query(text),
            timeout=self._timeout,
        )
        return self._projector.project_vector(raw_vec)

    def as_langchain_embeddings(self) -> Embeddings:
        return self._client
