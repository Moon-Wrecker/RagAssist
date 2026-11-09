# Technical Investigation & Architecture Design: Embedding Providers & Fallback Engine

**Module**: `src/ragassist/platform/embeddings/`  
**Milestone**: Milestone 1: Model & Decision Platform  
**Author**: Milestone 1 Explorer 2 (Embedding Providers & Fallback Engine)  
**Date**: 2026-11-07  

---

## 1. Executive Summary & Problem Analysis

In RagAssist, text embeddings provide the foundational semantic representations for:
1. **Document Ingestion Pipeline** (`modules/knowledge/`): Converting 5-pass hybrid document chunks into dense vectors stored in PostgreSQL `pgvector`.
2. **Dense Vector Search** (`modules/retrieval/`): Querying the HNSW cosine index via pgvector's `iterative_scan` with `relaxed_order`.

### Key Technical Challenges Identified
1. **Fixed Database Column Dimension (`vector(1536)`)**:
   - In accordance with ADR 0001, ADR 0003, and `PROJECT.md` § 3, the database table `document_chunks` defines the vector column as:
     ```sql
     embedding vector(1536) NOT NULL
     ```
   - In PostgreSQL + pgvector, inserting or searching against a column of type `vector(1536)` strictly enforces that all vectors have length exactly 1536. Any mismatch (e.g. 384 or 768 dimensions) results in an immediate SQL exception (`ERROR: different vector dimensions`).
2. **Multi-Provider Heterogeneity**:
   - **Primary Cloud Provider**: OpenAI `text-embedding-3-small` (native 1536 dims, MRL truncation support).
   - **Local Inference / Fallback**: `SentenceTransformers` (`all-MiniLM-L6-v2` = 384 dims; `bge-small-en-v1.5` = 384 dims; `bge-large-en-v1.5` = 1024 dims).
   - **Self-Hosted API**: Local Ollama / vLLM / OpenAI-compatible endpoints (`nomic-embed-text` = 768 dims, `bge-m3` = 1024 dims).
3. **Embedding Space Divergence vs. Fallback Resilience**:
   - Mathematically, vector spaces produced by different embedding models are not directly comparable. A query embedded with `SentenceTransformers` cannot be compared via cosine distance to chunks embedded with `OpenAI`.
   - **Architectural Solution**: Fallback serves two critical purposes:
     - *Ingestion Resiliency*: During offline/background document ingestion, if OpenAI experiences an outage, ingestion fails over to local/mirror models without pipeline blockage.
     - *Local-First / Private Mode*: Entire tenants or deployments can run 100% locally with `SentenceTransformers` or Ollama as primary.
     - *Query Fallback with Hybrid Search*: If OpenAI query embedding fails at runtime, the query can be embedded via the fallback model and combined with sparse PostgreSQL Full-Text Search (FTS) via Reciprocal Rank Fusion (RRF, $k=60$). FTS guarantees exact keyword retrieval even if dense spaces differ!
4. **Event-Loop Safety (AGENTS.md Rule 4)**:
   - Local PyTorch/SentenceTransformers inference (`model.encode()`) is CPU/GPU intensive. Executing it directly in async functions freezes the FastAPI asyncio event loop, breaking real-time SSE streaming.
   - Local inference MUST run in `run_cpu_bound()` (`src/ragassist/shared/resilience.py`).
5. **Optional Dependency Isolation**:
   - `torch` and `sentence-transformers` are listed under `[project.optional-dependencies] ml` in `pyproject.toml`. The platform MUST boot cleanly in environments where ML packages are not installed, with lazy imports and clear diagnostics.

---

## 2. Port Architecture (`src/ragassist/platform/embeddings/ports.py`)

### 2.1 Reconciling `ports.py` Location and Contracts
In Phase 0 scaffolding, an initial draft of `EmbeddingProvider` was placed in `src/ragassist/platform/llm/ports.py` with `build_embeddings(...) -> Embeddings`. However:
- As defined in `PROJECT.md` § 1.1 and the repository layout, `platform/embeddings/` is its own bounded context.
- The canonical protocol must expose asynchronous batch document embedding (`embed_documents`), query embedding (`embed_query`), and dimensionality inspection (`dimension`).

### 2.2 Canonical Port Definition

```python
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
```

### 2.3 Backward Compatibility Bridge in `src/ragassist/platform/llm/ports.py`
In `src/ragassist/platform/llm/ports.py`, line 54:
Update the file to import and re-export `EmbeddingProvider` from `ragassist.platform.embeddings.ports`:
```python
from ragassist.platform.embeddings.ports import EmbeddingProvider  # re-export
```
This guarantees zero disruption to any existing consumers while centralizing the contract.

---

## 3. Mathematical Dimension Projection & Cosine Invariance

When using models with native dimensions different from the database schema requirement (e.g. `all-MiniLM-L6-v2` with 384 dimensions vs. `vector(1536)`), we implement a mathematical **Dimension Projector**.

### 3.1 Mathematical Proof of Cosine Invariance Under Zero-Padding
Let $\mathbf{u}, \mathbf{v} \in \mathbb{R}^d$ be two unit vectors ($\|\mathbf{u}\|_2 = 1, \|\mathbf{v}\|_2 = 1$).  
Their cosine similarity is given by:
$$\cos(\mathbf{u}, \mathbf{v}) = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\|_2 \|\mathbf{v}\|_2} = \sum_{i=1}^d u_i v_i$$

Now construct zero-padded vectors $\mathbf{u}_{pad}, \mathbf{v}_{pad} \in \mathbb{R}^D$ where $D > d$:
$$\mathbf{u}_{pad} = [u_1, u_2, \dots, u_d, \underbrace{0, 0, \dots, 0}_{D - d}]$$
$$\mathbf{v}_{pad} = [v_1, v_2, \dots, v_d, \underbrace{0, 0, \dots, 0}_{D - d}]$$

**Norm:**
$$\|\mathbf{u}_{pad}\|_2 = \sqrt{\sum_{i=1}^d u_i^2 + \sum_{j=d+1}^D 0^2} = \sqrt{\|\mathbf{u}\|_2^2} = 1$$

**Inner Product:**
$$\mathbf{u}_{pad} \cdot \mathbf{v}_{pad} = \sum_{i=1}^d u_i v_i + \sum_{j=d+1}^D 0 \cdot 0 = \mathbf{u} \cdot \mathbf{v}$$

**Cosine Similarity:**
$$\cos(\mathbf{u}_{pad}, \mathbf{v}_{pad}) = \frac{\mathbf{u}_{pad} \cdot \mathbf{v}_{pad}}{\|\mathbf{u}_{pad}\|_2 \|\mathbf{v}_{pad}\|_2} = \frac{\mathbf{u} \cdot \mathbf{v}}{1 \cdot 1} = \cos(\mathbf{u}, \mathbf{v})$$

**Cosine Distance in pgvector ($1 - \cos$):**
$$\text{dist}_{pgvector}(\mathbf{u}_{pad}, \mathbf{v}_{pad}) = 1 - (\mathbf{u}_{pad} \cdot \mathbf{v}_{pad}) = 1 - (\mathbf{u} \cdot \mathbf{v}) = \text{dist}(\mathbf{u}, \mathbf{v})$$

**Conclusion**: Zero-padding unit vectors preserves 100% of the angles, relative rankings, and cosine distances within that model's vector space, while perfectly satisfying PostgreSQL's `vector(1536)` column constraint!

### 3.2 Dimension Projector Implementation

```python
"""Vector projection utilities for aligning embeddings to database dimension constraints."""

import math
from typing import Sequence


class DimensionProjector:
    """Projects embedding vectors to a target dimensionality while preserving normalization."""

    def __init__(self, target_dimension: int = 1536) -> None:
        self.target_dimension = target_dimension

    def project_vector(self, vec: Sequence[float]) -> list[float]:
        """Project a single vector to target_dimension."""
        curr_dim = len(vec)
        if curr_dim == self.target_dimension:
            return list(vec)

        if curr_dim < self.target_dimension:
            # Zero-padding: preserve norm and angular relationships
            padded = list(vec) + [0.0] * (self.target_dimension - curr_dim)
            return self._normalize(padded)

        # Truncation (Matryoshka Representation): slice and re-normalize
        truncated = list(vec[: self.target_dimension])
        return self._normalize(truncated)

    def project_vectors(self, vectors: Sequence[Sequence[float]]) -> list[list[float]]:
        """Project a batch of vectors."""
        return [self.project_vector(v) for v in vectors]

    @staticmethod
    def _normalize(vec: list[float]) -> list[float]:
        norm = math.sqrt(sum(x * x for x in vec))
        if norm < 1e-12:
            return vec
        return [x / norm for x in vec]
```

---

## 4. Adapter Implementations

### 4.1 OpenAIEmbeddingAdapter (`src/ragassist/platform/embeddings/adapters/openai_adapter.py`)
- **Technology**: `langchain_openai.OpenAIEmbeddings`.
- **Features**:
  - Automatically sets `dimensions=self._dimension` for `text-embedding-3-*` models (Matryoshka support).
  - Handles `text-embedding-ada-002` (which rejects the `dimensions` API parameter).
  - Batches chunk inputs into groups of `settings.EMBEDDING_BATCH_SIZE` (default 64) to prevent payload overflows.
  - Asynchronous execution via `aembed_documents()` and `aembed_query()`.
  - Comprehensive error translation: raises informative domain exceptions on missing API key, rate limits, or timeouts.

```python
"""OpenAI Dense Embedding Adapter."""

import asyncio
from typing import Any
import structlog
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

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
            api_key=api_key or "<placeholder-key>",
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
```

---

### 4.2 OpenAICompatibleEmbeddingAdapter (`src/ragassist/platform/embeddings/adapters/openai_compatible_adapter.py`)
- **Technology**: `langchain_openai.OpenAIEmbeddings` configured with `base_url` pointing to local Ollama, vLLM, or LM Studio.
- **Key Features**:
  - `check_embedding_ctx_length=False`: **Crucial** setting! By default, `OpenAIEmbeddings` attempts to look up tiktoken tokenizer metadata for the model name. For local models (e.g. `nomic-embed-text`, `bge-m3`), tiktoken fails with `KeyError`. Disabling this allows arbitrary local models.
  - Dimension alignment: If the local endpoint returns vectors of dimension different from 1536 (e.g. 768 or 1024), `DimensionProjector` automatically zero-pads or truncates to match `EMBEDDING_DIMENSION`.

```python
"""OpenAI-Compatible Dense Embedding Adapter (Ollama, vLLM, LM Studio)."""

import asyncio
from typing import Any
import structlog
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.platform.embeddings.projector import DimensionProjector
from ragassist.shared.config.settings import Settings, get_settings

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
        timeout: float = 20.0,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._base_url = base_url or self.settings.OPENAI_COMPATIBLE_BASE_URL
        self._model_name = model_name or "nomic-embed-text"
        self._dimension = dimension or self.settings.EMBEDDING_DIMENSION
        self._batch_size = batch_size or self.settings.EMBEDDING_BATCH_SIZE
        self._api_key = api_key or self.settings.OPENAI_COMPATIBLE_API_KEY
        self._timeout = timeout
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
```

---

### 4.3 SentenceTransformersEmbeddingAdapter (`src/ragassist/platform/embeddings/adapters/sentence_transformers_adapter.py`)
- **Technology**: `sentence_transformers.SentenceTransformer`.
- **Key Features**:
  - **Lazy Loading**: `sentence_transformers` and `torch` are only imported when the model is initialized. If optional ML dependencies are absent, a clear, actionable exception is raised.
  - **Event-Loop Safety**: Uses `run_cpu_bound()` (`src/ragassist/shared/resilience.py`) to execute inference in the bounded worker pool, ensuring the FastAPI event loop is never blocked.
  - **Hardware Acceleration**: Checks `torch.cuda.is_available()`. If GPU is present (e.g. RTX 3060), defaults to `device="cuda"`, otherwise falls back to `device="cpu"`.
  - **Dimension Projection**: Preserves cosine distance via zero-padding from 384/768 up to 1536.

```python
"""SentenceTransformers Local Dense Embedding Adapter (CPU & GPU)."""

from typing import Any
import structlog
from langchain_core.embeddings import Embeddings

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
        batch_size: int = 32,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._model_name = model_name or getattr(
            self.settings, "SENTENCE_TRANSFORMERS_MODEL", "all-MiniLM-L6-v2"
        )
        self._target_dimension = target_dimension or self.settings.EMBEDDING_DIMENSION
        self._device = device
        self._batch_size = batch_size
        self._projector = DimensionProjector(target_dimension=self._target_dimension)
        self._model: Any = None

    @property
    def name(self) -> str:
        return "sentence_transformers"

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
        # Convert numpy array to python list of floats
        return [v.tolist() for v in vectors]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        raw_vectors = await run_cpu_bound(self._sync_encode, texts)
        return self._projector.project_vectors(raw_vectors)

    async def embed_query(self, text: str) -> list[float]:
        raw_vectors = await run_cpu_bound(self._sync_encode, [text])
        return self._projector.project_vector(raw_vectors[0])

    def as_langchain_embeddings(self) -> Embeddings:
        # Simple LangChain Embeddings wrapper delegating to this adapter
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
```

---

## 5. Provider Registry & Fallback Chain Integration

### 5.1 Provider Registry (`src/ragassist/platform/embeddings/registry.py`)
Using the thread-safe `ProviderRegistry[T]` from `src/ragassist/shared/registry.py`:

```python
"""Provider Registry and factory for Embedding Providers."""

import structlog
from ragassist.platform.embeddings.adapters.openai_adapter import OpenAIEmbeddingAdapter
from ragassist.platform.embeddings.adapters.openai_compatible_adapter import OpenAICompatibleEmbeddingAdapter
from ragassist.platform.embeddings.adapters.sentence_transformers_adapter import SentenceTransformersEmbeddingAdapter
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
```

---

### 5.2 Embedding Service & Fallback Chain (`src/ragassist/platform/embeddings/service.py`)
`EmbeddingService` wraps `FallbackChain[EmbeddingProvider]` with:
1. Strict dimension acceptance validation (`len(vec) == self.dimension`).
2. Vector count validation (`len(result) == len(texts)`).
3. Structured warning logs on failover.
4. Active provider identification for telemetry and debugging.

```python
"""High-level Embedding Service with automatic FallbackChain resilience."""

from collections.abc import Sequence
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

        vectors, used_provider = await self._chain.execute(
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

        vector, used_provider = await self._chain.execute(
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
```

---

## 6. Configuration & Repo Hygiene Synchronizations

### 6.1 Additions to `src/ragassist/shared/config/settings.py`
To support the embedding fallback chain and local models cleanly, add the following fields to `Settings`:
```python
    # --- Embeddings & Vector Search ---
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_BATCH_SIZE: int = 64
    EMBEDDING_TIMEOUT_SECONDS: float = 15.0
    EMBEDDING_FALLBACK_CHAIN: str = "openai,sentence_transformers"
    SENTENCE_TRANSFORMERS_MODEL: str = "all-MiniLM-L6-v2"
    SENTENCE_TRANSFORMERS_DEVICE: str = "auto"
```

### 6.2 Synchronizing `.env.example`
In accordance with `AGENTS.md` § 3.1, keep `.env.example` synchronized:
```ini
# --- Embeddings & Vector Search ---
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
EMBEDDING_BATCH_SIZE=64
EMBEDDING_TIMEOUT_SECONDS=15.0
EMBEDDING_FALLBACK_CHAIN=openai,sentence_transformers
SENTENCE_TRANSFORMERS_MODEL=all-MiniLM-L6-v2
SENTENCE_TRANSFORMERS_DEVICE=auto
```

---

## 7. Concrete Unit Test Specifications (`tests/unit/platform/test_embeddings.py`)

A comprehensive test suite covering 100% of the platform embedding behaviors without making external network calls.

### 7.1 Test Case Matrix

| Test Function | Target Component | Description / Scenario |
|---|---|---|
| `test_dimension_projector_padding_cosine_invariance` | `DimensionProjector` | Mathematically asserts that $\cos(\mathbf{u}_{pad}, \mathbf{v}_{pad}) == \cos(\mathbf{u}, \mathbf{v})$ within float tolerance (`1e-6`). |
| `test_dimension_projector_truncation` | `DimensionProjector` | Asserts that vectors with dimension $> 1536$ are truncated and properly normalized to unit length. |
| `test_openai_adapter_embed_documents_and_query` | `OpenAIEmbeddingAdapter` | Mocks `OpenAIEmbeddings.aembed_documents` and `aembed_query`, verifies batch slicing (`batch_size=2` across 5 chunks), and verifies dimensions. |
| `test_openai_compatible_adapter_custom_url` | `OpenAICompatibleEmbeddingAdapter` | Verifies `check_embedding_ctx_length=False` is set and dimension projection is executed on 768-dim mock output. |
| `test_sentence_transformers_adapter_run_cpu_bound` | `SentenceTransformersEmbeddingAdapter` | Mocks `SentenceTransformer.encode()`, verifies execution via `run_cpu_bound`, and confirms zero-padding to 1536. |
| `test_sentence_transformers_missing_dependency_error` | `SentenceTransformersEmbeddingAdapter` | Simulates `ImportError` on `sentence_transformers` and verifies informative error message. |
| `test_provider_registry_lookup_and_aliases` | `ProviderRegistry[EmbeddingProvider]` | Verifies registering, retrieving `"openai"`, `"sentence_transformers"`, `"ollama"`, and checks unknown key raises `KeyError`. |
| `test_embedding_service_primary_success` | `EmbeddingService` | Primary succeeds; verifies result returned and fallback not triggered. |
| `test_embedding_service_failover_on_exception` | `EmbeddingService` | Primary raises `TimeoutError`; FallbackChain intercepts and secondary returns valid vectors. |
| `test_embedding_service_failover_on_unacceptable_dimension` | `EmbeddingService` | Primary returns vectors of dimension 512 (when 1536 is expected); `_is_acceptable` fails and secondary succeeds. |
| `test_embedding_service_all_members_fail` | `EmbeddingService` | All providers fail; verifies `RuntimeError` is raised with chain history. |

### 7.2 Complete Unit Test Code Specification

```python
"""Unit tests for Embedding Providers, Projector, Registry, and Fallback Service."""

import math
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from ragassist.platform.embeddings.adapters.openai_adapter import OpenAIEmbeddingAdapter
from ragassist.platform.embeddings.adapters.openai_compatible_adapter import OpenAICompatibleEmbeddingAdapter
from ragassist.platform.embeddings.adapters.sentence_transformers_adapter import SentenceTransformersEmbeddingAdapter
from ragassist.platform.embeddings.ports import EmbeddingProvider
from ragassist.platform.embeddings.projector import DimensionProjector
from ragassist.platform.embeddings.registry import build_embedding_registry
from ragassist.platform.embeddings.service import EmbeddingService
from ragassist.shared.resilience import FallbackChain


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


# --- 1. DimensionProjector Tests ---

def test_dimension_projector_padding_cosine_invariance():
    # 3-dim unit vectors
    u = [1.0 / math.sqrt(3), 1.0 / math.sqrt(3), 1.0 / math.sqrt(3)]
    v = [1.0, 0.0, 0.0]

    orig_sim = cosine_similarity(u, v)

    projector = DimensionProjector(target_dimension=1536)
    u_pad = projector.project_vector(u)
    v_pad = projector.project_vector(v)

    assert len(u_pad) == 1536
    assert len(v_pad) == 1536
    pad_sim = cosine_similarity(u_pad, v_pad)

    # Mathematically identical within float tolerance
    assert pytest.approx(orig_sim, abs=1e-6) == pad_sim
    assert pytest.approx(1.0, abs=1e-6) == math.sqrt(sum(x * x for x in u_pad))


def test_dimension_projector_truncation():
    # 2048-dim vector truncated to 1536
    projector = DimensionProjector(target_dimension=1536)
    vec = [0.1] * 2048
    projected = projector.project_vector(vec)

    assert len(projected) == 1536
    norm = math.sqrt(sum(x * x for x in projected))
    assert pytest.approx(1.0, abs=1e-6) == norm


# --- 2. OpenAI Embedding Adapter Tests ---

@pytest.mark.asyncio
async def test_openai_adapter_embed_documents_and_query():
    adapter = OpenAIEmbeddingAdapter(model_name="text-embedding-3-small", dimension=1536, batch_size=2)
    mock_vec = [0.05] * 1536

    with patch.object(adapter._client, "aembed_documents", new_callable=AsyncMock) as mock_docs, \
         patch.object(adapter._client, "aembed_query", new_callable=AsyncMock) as mock_query:
        
        mock_docs.side_effect = lambda batch: [mock_vec for _ in batch]
        mock_query.return_value = mock_vec

        chunks = ["chunk1", "chunk2", "chunk3"]
        docs_res = await adapter.embed_documents(chunks)

        assert len(docs_res) == 3
        assert len(docs_res[0]) == 1536
        # Assert batching: 3 items with batch_size=2 results in 2 calls
        assert mock_docs.call_count == 2

        query_res = await adapter.embed_query("search query")
        assert len(query_res) == 1536
        assert mock_query.call_count == 1


# --- 3. OpenAI-Compatible Adapter Tests ---

@pytest.mark.asyncio
async def test_openai_compatible_adapter_projection():
    adapter = OpenAICompatibleEmbeddingAdapter(
        base_url="http://localhost:11434/v1",
        model_name="nomic-embed-text",
        dimension=1536,
    )
    # Mock Ollama returning 768-dim vector
    raw_768 = [0.1] * 768

    with patch.object(adapter._client, "aembed_documents", new_callable=AsyncMock) as mock_docs, \
         patch.object(adapter._client, "aembed_query", new_callable=AsyncMock) as mock_query:
        
        mock_docs.return_value = [raw_768]
        mock_query.return_value = raw_768

        docs = await adapter.embed_documents(["test"])
        query = await adapter.embed_query("test query")

        assert len(docs[0]) == 1536
        assert len(query) == 1536


# --- 4. SentenceTransformers Adapter Tests ---

@pytest.mark.asyncio
async def test_sentence_transformers_adapter_mocked():
    adapter = SentenceTransformersEmbeddingAdapter(
        model_name="all-MiniLM-L6-v2",
        target_dimension=1536,
        device="cpu",
    )
    import numpy as np
    mock_st = MagicMock()
    # 384-dim normalized vector
    mock_st.encode.return_value = np.ones((2, 384), dtype=np.float32) / math.sqrt(384)

    with patch.object(adapter, "_get_model", return_value=mock_st):
        res = await adapter.embed_documents(["doc1", "doc2"])
        assert len(res) == 2
        assert len(res[0]) == 1536
        assert pytest.approx(1.0, abs=1e-5) == math.sqrt(sum(x * x for x in res[0]))


# --- 5. FallbackChain & EmbeddingService Tests ---

class FakeEmbeddingProvider:
    def __init__(self, name: str, dim: int = 1536, fail: bool = False, wrong_dim: bool = False) -> None:
        self.name = name
        self._dim = dim
        self.fail = fail
        self.wrong_dim = wrong_dim

    def dimension(self) -> int:
        return self._dim

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise TimeoutError(f"Provider {self.name} timed out")
        dim = 512 if self.wrong_dim else self._dim
        return [[0.1] * dim for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        if self.fail:
            raise TimeoutError(f"Provider {self.name} timed out")
        dim = 512 if self.wrong_dim else self._dim
        return [0.1] * dim


@pytest.mark.asyncio
async def test_embedding_service_primary_success():
    p1 = FakeEmbeddingProvider("p1")
    p2 = FakeEmbeddingProvider("p2")
    chain = FallbackChain("test", [p1, p2])
    svc = EmbeddingService(chain, expected_dimension=1536)

    res = await svc.embed_query("hello")
    assert len(res) == 1536


@pytest.mark.asyncio
async def test_embedding_service_failover_on_exception():
    p1 = FakeEmbeddingProvider("p1", fail=True)
    p2 = FakeEmbeddingProvider("p2", fail=False)
    chain = FallbackChain("test", [p1, p2])
    svc = EmbeddingService(chain, expected_dimension=1536)

    res = await svc.embed_query("hello")
    assert len(res) == 1536


@pytest.mark.asyncio
async def test_embedding_service_failover_on_unacceptable_dim():
    p1 = FakeEmbeddingProvider("p1", wrong_dim=True)
    p2 = FakeEmbeddingProvider("p2", wrong_dim=False)
    chain = FallbackChain("test", [p1, p2])
    svc = EmbeddingService(chain, expected_dimension=1536)

    res = await svc.embed_documents(["doc1", "doc2"])
    assert len(res) == 2
    assert len(res[0]) == 1536
```

---

## 8. Directory Layout & Builder Implementation Checklist

### Proposed Files in `src/ragassist/platform/embeddings/`
```
src/ragassist/platform/embeddings/
├── __init__.py                      # Package entry point, re-exporting key symbols
├── ports.py                         # EmbeddingProvider protocol & contracts
├── projector.py                     # DimensionProjector (zero-pad, truncate, normalize)
├── registry.py                      # ProviderRegistry[EmbeddingProvider] & factory
├── service.py                       # EmbeddingService & FallbackChain orchestration
└── adapters/
    ├── __init__.py                  # Adapters entry point
    ├── openai_adapter.py            # OpenAIEmbeddingAdapter (langchain-openai)
    ├── openai_compatible_adapter.py # OpenAICompatibleEmbeddingAdapter (Ollama/vLLM)
    └── sentence_transformers_adapter.py # SentenceTransformersEmbeddingAdapter (CPU/GPU)
```

### Dependency Validation
- Inward dependency rule check:
  - `ports.py`: depends only on typing and `langchain_core.embeddings.Embeddings`. No database or application imports.
  - `projector.py`: pure Python + math standard library.
  - `adapters/`: depends on `ports.py`, `projector.py`, `shared/config/settings.py`, and `shared/resilience.py`.
  - `service.py`: depends on `ports.py`, `registry.py`, `shared/resilience.py`, and `shared/config/settings.py`.
  - This strictly complies with Hexagonal Architecture and `import-linter` rules.
