"""SentenceTransformers Local Dense Embedding Adapter (CPU & GPU)."""

from typing import Any
from langchain_core.embeddings import Embeddings
import structlog

from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.platform.embeddings.projector import DimensionProjector
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.resilience import run_cpu_bound

logger = structlog.get_logger(__name__)


class SentenceTransformersEmbeddingAdapter(EmbeddingProvider):
    """Adapter for local SentenceTransformer models running on CPU or NVIDIA GPU."""

    def __init__(
        self,
        model_name: str | None = None,
        target_dimension: int | None = None,
        device: str | None = None,
        batch_size: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._model_name = model_name or getattr(
            self.settings, "SENTENCE_TRANSFORMERS_MODEL", "all-MiniLM-L6-v2"
        )
        self._target_dimension = target_dimension or self.settings.EMBEDDING_DIMENSION
        self._device = device
        self._batch_size = batch_size if batch_size is not None else self.settings.EMBEDDING_BATCH_SIZE
        self._projector = DimensionProjector(target_dimension=self._target_dimension)
        self._model: Any = None

    @property
    def name(self) -> str:
        return "sentence_transformers"

    @property
    def model_name(self) -> str:
        """The configured model; part of the embedding cache key (a new model must never reuse old vectors)."""
        return str(self._model_name)

    def dimension(self) -> int:
        return self._target_dimension

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
            import torch
        except ImportError as exc:
            raise ImportError(
                "SentenceTransformersEmbeddingAdapter requires 'sentence-transformers' and 'torch'. "
                "Install them via 'uv pip install -e .[ml]'"
            ) from exc

        device = self._device
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(
            "sentence_transformers.init",
            model=self._model_name,
            device=device,
            target_dim=self._target_dimension,
        )
        self._model = SentenceTransformer(self._model_name, device=device)
        return self._model

    def _sync_encode(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        # Convert numpy array / list to python list of floats
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        raw_vectors = await run_cpu_bound(self._sync_encode, texts)
        return self._projector.project_vectors(raw_vectors)

    async def embed_query(self, text: str) -> list[float]:
        raw_vectors = await run_cpu_bound(self._sync_encode, [text])
        return self._projector.project_vector(raw_vectors[0])

    def as_langchain_embeddings(self) -> Embeddings:
        adapter = self

        class _LangChainBridge(Embeddings):
            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                raw = adapter._sync_encode(texts)
                return adapter._projector.project_vectors(raw)

            def embed_query(self, text: str) -> list[float]:
                raw = adapter._sync_encode([text])
                return adapter._projector.project_vector(raw[0])

            async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
                return await adapter.embed_documents(texts)

            async def aembed_query(self, text: str) -> list[float]:
                return await adapter.embed_query(text)

        return _LangChainBridge()
