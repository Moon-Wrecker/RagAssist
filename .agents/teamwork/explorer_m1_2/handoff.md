# Handoff Report: Embedding Providers & Fallback Engine Architecture

**Agent**: Milestone 1 Explorer 2 (`explorer_m1_2`)  
**Parent**: `be9621e6-d3bc-446a-abb9-2d0c46239ab1`  
**Task**: Technical investigation, architecture design, and test specifications for Dense Embedding Providers and Fallback Engine (`src/ragassist/platform/embeddings/`).  
**Handoff Type**: Hard (Investigation & Design Complete)  

---

## 1. Observation

1. **Existing Codebase State**:
   - `src/ragassist/platform/llm/ports.py` (lines 54-70) defines an early `EmbeddingProvider` Protocol with `build_embeddings(model_name: str, **extra_kwargs: Any) -> Embeddings`.
   - `src/ragassist/platform/embeddings/` contains only empty `__init__.py` files (`platform/embeddings/__init__.py` and `platform/embeddings/adapters/__init__.py`).
   - `src/ragassist/shared/config/settings.py` (lines 80-83) specifies:
     - `EMBEDDING_PROVIDER: str = "openai"`
     - `EMBEDDING_MODEL: str = "text-embedding-3-small"`
     - `EMBEDDING_DIMENSION: int = 1536`
     - `EMBEDDING_BATCH_SIZE: int = 64`
     - Missing explicit embedding fallback chain, timeout, and sentence-transformers model settings.
   - `pyproject.toml` (lines 47-50) specifies:
     - `[project.optional-dependencies] ml = ["torch>=2.4.0", "sentence-transformers>=3.1.0"]`.
     - Inspection of `.venv` revealed `torch` and `sentence-transformers` are not pre-installed in the default virtual environment; only core dependencies like `langchain-openai` are installed.
2. **Database Schema & Dimension Contract**:
   - PostgreSQL table `document_chunks` (ADR 0001, ADR 0003, `PROJECT.md` § 3) specifies: `embedding vector(1536)`.
   - pgvector strictly checks vector length against the column declaration. Passing any vector not of dimension 1536 throws a fatal database exception (`ERROR: different vector dimensions 1536 and <dim>`).
3. **Resilience Utilities**:
   - `src/ragassist/shared/registry.py` provides `ProviderRegistry[T]`.
   - `src/ragassist/shared/resilience.py` provides `FallbackChain[T]` and `run_cpu_bound()`.

---

## 2. Logic Chain

1. **Port Decoupling**:
   - `platform/embeddings/` is an independent horizontal platform package. The canonical `EmbeddingProvider` protocol belongs in `src/ragassist/platform/embeddings/ports.py`, exposing async `embed_documents(texts: list[str]) -> list[list[float]]`, `embed_query(text: str) -> list[float]`, and `dimension() -> int`.
   - `src/ragassist/platform/llm/ports.py` should import and re-export `EmbeddingProvider` from `platform/embeddings/ports.py` to maintain backward compatibility and avoid divergent definitions.
2. **Dimension Alignment & Invariance**:
   - Models like `all-MiniLM-L6-v2` output 384 dimensions, while Ollama models (e.g. `nomic-embed-text`) output 768 dimensions.
   - For unit vectors, zero-padding to 1536 mathematically preserves cosine distance exactly:
     $$\mathbf{u}_{pad} \cdot \mathbf{v}_{pad} = \sum_{i=1}^d u_i v_i + \sum_{j=d+1}^{1536} 0 = \mathbf{u} \cdot \mathbf{v}$$
   - Zero-padding provides an exact isometric embedding into $\mathbb{R}^{1536}$ that satisfies PostgreSQL schema constraints with zero distortion within the model's vector space.
   - `DimensionProjector` implements zero-padding for $d < 1536$ and Matryoshka truncation + normalization for $d > 1536$.
3. **Adapter Designs**:
   - `OpenAIEmbeddingAdapter`: wraps `langchain_openai.OpenAIEmbeddings`, enforces `dimensions=1536` on `text-embedding-3-*` models, implements batch chunking (`batch_size=64`), and executes asynchronously.
   - `OpenAICompatibleEmbeddingAdapter`: wraps `OpenAIEmbeddings` with `base_url` (Ollama/vLLM) and explicitly disables `check_embedding_ctx_length` (setting it to `False`) to prevent tiktoken crashes on local model names. Employs `DimensionProjector`.
   - `SentenceTransformersEmbeddingAdapter`: lazily loads `sentence_transformers` and `torch`, detects CUDA (RTX 3060), executes CPU/GPU inference via `run_cpu_bound()` to protect the asyncio event loop, and applies `DimensionProjector`.
4. **Fallback Chain & Service**:
   - `build_embedding_registry()` registers `"openai"`, `"openai_compatible"`, and `"sentence_transformers"`.
   - `EmbeddingService` coordinates `FallbackChain[EmbeddingProvider]` with strict validation on every result: verifying `len(result) == len(texts)` and `all(len(vec) == 1536)`. If a member fails or produces invalid dimensionality, the chain automatically cascades.

---

## 3. Caveats

1. **Cross-Model Vector Search Incompatibility**:
   - While zero-padding preserves relative distances *within* a single model's vectors, vectors from different embedding models (e.g., OpenAI vs. SentenceTransformers) occupy different latent spaces and cannot be meaningfully compared.
   - *Impact on Fallback*: If OpenAI fails during a live search query, searching against documents embedded with OpenAI using fallback embeddings will yield lower dense cosine recall. However, RagAssist's hybrid retrieval architecture (ADR 0001, ADR 0005) combines dense search with sparse PostgreSQL Full-Text Search (FTS) via Reciprocal Rank Fusion (RRF, $k=60$), ensuring exact keyword hits still succeed during dense provider outages.
2. **Optional Dependency `[ml]`**:
   - `SentenceTransformersEmbeddingAdapter` requires `torch` and `sentence-transformers`. If not installed in `.venv`, attempts to execute this adapter will raise an informative `ImportError`. The fallback chain must gracefully log and continue to another member if one is available.

---

## 4. Conclusion

The embedding provider architecture for Milestone 1 is completely designed and specified in `analysis_embeddings.md`. The design:
1. Satisfies Hexagonal Architecture and `AGENTS.md` layering rules.
2. Prevents event-loop starvation by offloading local ML inference to `run_cpu_bound()`.
3. Solves the PostgreSQL `vector(1536)` database constraint via mathematically proven zero-padding projection.
4. Provides full multi-provider fallback resilience via `FallbackChain[EmbeddingProvider]`.
5. Includes a complete unit test specification with 11 test cases and mock strategies.

The builder agent can directly proceed to implementation using the class signatures and file layout documented in `analysis_embeddings.md`.

---

## 5. Verification Method

To independently verify the recommendations once implemented by the builder:

1. **Verify Inward Dependency & Linting**:
   ```powershell
   .\.venv\Scripts\ruff check src/ragassist/platform/embeddings/
   .\.venv\Scripts\mypy src/ragassist/platform/embeddings/
   ```
2. **Verify Unit Tests**:
   ```powershell
   $env:PYTHONPATH="src"
   .\.venv\Scripts\python -m pytest tests/unit/platform/test_embeddings.py -v
   ```
3. **Verify Dimension Invariance Assertion**:
   Run the test case `test_dimension_projector_padding_cosine_invariance` to assert that cosine similarity is identical before and after zero-padding to 1536.
4. **Inspect Files**:
   - `src/ragassist/platform/embeddings/ports.py`
   - `src/ragassist/platform/embeddings/projector.py`
   - `src/ragassist/platform/embeddings/adapters/openai_adapter.py`
   - `src/ragassist/platform/embeddings/adapters/openai_compatible_adapter.py`
   - `src/ragassist/platform/embeddings/adapters/sentence_transformers_adapter.py`
   - `src/ragassist/platform/embeddings/registry.py`
   - `src/ragassist/platform/embeddings/service.py`
   - `tests/unit/platform/test_embeddings.py`
