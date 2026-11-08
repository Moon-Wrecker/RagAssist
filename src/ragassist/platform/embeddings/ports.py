"""Abstract ports and contracts for Dense Embedding providers."""

from typing import Protocol, runtime_checkable
from langchain_core.embeddings import Embeddings


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for generating dense vector embeddings."""

    @property
    def name(self) -> str:
        """Provider adapter identifier (e.g. 'openai', 'sentence_transformers', 'openai_compatible')."""
        ...

    def dimension(self) -> int:
        """Vector dimensionality produced by this provider (e.g. 1536)."""
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate dense embeddings for a list of document chunk texts.

        Args:
            texts: List of text chunks to embed.

        Returns:
            List of embedding vectors, where each vector length equals dimension().
        """
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Generate a dense embedding for a single user query.

        Args:
            text: Query text string.

        Returns:
            An embedding vector of length dimension().
        """
        ...

    def as_langchain_embeddings(self) -> Embeddings:
        """Return a LangChain-compatible Embeddings instance for vectorstores/retrievers."""
        ...
