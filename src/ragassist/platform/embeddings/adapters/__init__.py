"""Embedding provider adapters."""

from ragassist.platform.embeddings.adapters.openai_adapter import OpenAIEmbeddingAdapter
from ragassist.platform.embeddings.adapters.openai_compatible_adapter import (
    OpenAICompatibleEmbeddingAdapter,
)
from ragassist.platform.embeddings.adapters.sentence_transformers_adapter import (
    SentenceTransformersEmbeddingAdapter,
)

__all__ = [
    "OpenAICompatibleEmbeddingAdapter",
    "OpenAIEmbeddingAdapter",
    "SentenceTransformersEmbeddingAdapter",
]
