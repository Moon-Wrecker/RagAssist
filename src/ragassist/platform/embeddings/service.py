"""High-level Embedding Service with automatic FallbackChain resilience."""

import structlog

from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.platform.embeddings.registry import build_embedding_registry
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.resilience import FallbackChain

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Service orchestrating dense embeddings with automatic failover across providers."""

    def __init__(
        self,
        chain: FallbackChain[EmbeddingProvider],
        expected_dimension: int = 1536,
    ) -> None:
        self._chain = chain
        self._expected_dimension = expected_dimension

    @property
    def dimension(self) -> int:
        return self._expected_dimension

    @property
    def members(self) -> list[EmbeddingProvider]:
        return list(self._chain.members)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        async def _operation(provider: EmbeddingProvider) -> list[list[float]]:
            return await provider.embed_documents(texts)

        def _is_acceptable(vectors: list[list[float]]) -> bool:
            if not vectors or len(vectors) != len(texts):
                return False
            # Verify each vector matches required pgvector dimension
            return all(len(v) == self._expected_dimension for v in vectors)

        vectors, _used_provider = await self._chain.execute(
            operation=_operation,
            is_acceptable=_is_acceptable,
        )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        if not text or not text.strip():
            return [0.0] * self._expected_dimension

        async def _operation(provider: EmbeddingProvider) -> list[float]:
            return await provider.embed_query(text)

        def _is_acceptable(vector: list[float]) -> bool:
            return len(vector) == self._expected_dimension

        vector, _used_provider = await self._chain.execute(
            operation=_operation,
            is_acceptable=_is_acceptable,
        )
        return vector


def build_embedding_service(settings: Settings | None = None) -> EmbeddingService:
    """Factory creating an EmbeddingService initialized with configured FallbackChain."""
    cfg = settings or get_settings()
    registry = build_embedding_registry(cfg)

    # Parse fallback chain string: e.g. "openai,sentence_transformers"
    chain_keys_raw = getattr(cfg, "EMBEDDING_FALLBACK_CHAIN", "openai,sentence_transformers")
    chain_keys = [k.strip().lower() for k in chain_keys_raw.split(",") if k.strip()]

    providers: list[EmbeddingProvider] = []
    for key in chain_keys:
        if registry.is_registered(key):
            providers.append(registry.create(key))
        else:
            logger.warning("embedding_service.unknown_provider", key=key)

    if not providers:
        # Fallback to default openai adapter
        providers = [registry.create("openai")]

    chain = FallbackChain[EmbeddingProvider](name="embeddings_chain", members=providers)
    return EmbeddingService(chain=chain, expected_dimension=cfg.EMBEDDING_DIMENSION)
