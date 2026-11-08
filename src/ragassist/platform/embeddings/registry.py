"""Provider Registry and factory for Embedding Providers."""

import structlog

from ragassist.platform.embeddings.adapters.openai_adapter import OpenAIEmbeddingAdapter
from ragassist.platform.embeddings.adapters.openai_compatible_adapter import (
    OpenAICompatibleEmbeddingAdapter,
)
from ragassist.platform.embeddings.adapters.sentence_transformers_adapter import (
    SentenceTransformersEmbeddingAdapter,
)
from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.registry import ProviderRegistry

logger = structlog.get_logger(__name__)


def build_embedding_registry(settings: Settings | None = None) -> ProviderRegistry[EmbeddingProvider]:
    """Build and register standard embedding providers."""
    cfg = settings or get_settings()
    registry: ProviderRegistry[EmbeddingProvider] = ProviderRegistry("EmbeddingProvider")

    registry.register("openai", lambda: OpenAIEmbeddingAdapter(settings=cfg))
    registry.register("openai_compatible", lambda: OpenAICompatibleEmbeddingAdapter(settings=cfg))
    registry.register("sentence_transformers", lambda: SentenceTransformersEmbeddingAdapter(settings=cfg))

    # Aliases
    registry.register("ollama", lambda: OpenAICompatibleEmbeddingAdapter(settings=cfg))
    registry.register("local", lambda: SentenceTransformersEmbeddingAdapter(settings=cfg))

    return registry
