"""Dense embedding platform package."""

from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.platform.embeddings.projector import DimensionProjector
from ragassist.platform.embeddings.registry import build_embedding_registry
from ragassist.platform.embeddings.service import EmbeddingService, build_embedding_service

__all__ = [
    "DimensionProjector",
    "EmbeddingProvider",
    "EmbeddingService",
    "build_embedding_registry",
    "build_embedding_service",
]
