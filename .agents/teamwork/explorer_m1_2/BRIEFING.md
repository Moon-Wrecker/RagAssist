# BRIEFING — 2026-11-07T20:32:00Z

## Mission
Investigate and design Embedding Providers and Fallback Engine for Milestone 1: Model & Decision Platform.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigation, synthesis, recommendation
- Working directory: d:\Coding\RagAssist-1
- State folder: d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_2
- Original parent: be9621e6-d3bc-446a-abb9-2d0c46239ab1
- Milestone: Milestone 1: Model & Decision Platform

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Do NOT write source code in src/ or tests/
- Write only to state folder: d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_2

## Current Parent
- Conversation ID: be9621e6-d3bc-446a-abb9-2d0c46239ab1
- Updated: 2026-11-07T20:32:00Z

## Investigation State
- **Explored paths**:
  - `src/ragassist/platform/llm/ports.py` (line 54-70 EmbeddingProvider Protocol draft)
  - `src/ragassist/platform/embeddings/` (skeleton structure with empty `__init__.py`)
  - `src/ragassist/shared/config/settings.py` (EMBEDDING_PROVIDER, EMBEDDING_MODEL, EMBEDDING_DIMENSION=1536)
  - `src/ragassist/shared/registry.py` (ProviderRegistry[T])
  - `src/ragassist/shared/resilience.py` (FallbackChain[T], run_cpu_bound)
  - `pyproject.toml` (optional ml dependencies torch & sentence-transformers)
  - `docs/adr/0001-pgvector-unified-storage.md` and database schema constraints (vector(1536))
- **Key findings**:
  - `vector(1536)` in PostgreSQL rejects any mismatched dimensions with a fatal transaction abort.
  - Zero-padding unit vectors from 384/768 to 1536 is an exact mathematical isometry for cosine similarity: $\cos(\mathbf{u}_{pad}, \mathbf{v}_{pad}) = \cos(\mathbf{u}, \mathbf{v})$.
  - OpenAI-compatible adapter must set `check_embedding_ctx_length=False` to prevent tiktoken crashes on local model names.
  - Local PyTorch/SentenceTransformers inference must execute via `run_cpu_bound()` to protect the asyncio event loop.
  - ML dependencies must be lazily imported since they are optional.
- **Unexplored areas**: None. Complete investigation finished.

## Key Decisions Made
- Canonical `EmbeddingProvider` protocol placed in `src/ragassist/platform/embeddings/ports.py` with async `embed_documents`, async `embed_query`, and `dimension()`. Re-exported in `platform/llm/ports.py`.
- Designed `DimensionProjector` implementing zero-padding and Matryoshka truncation + normalization.
- Designed `OpenAIEmbeddingAdapter`, `OpenAICompatibleEmbeddingAdapter`, and `SentenceTransformersEmbeddingAdapter`.
- Designed `build_embedding_registry()` and `EmbeddingService` coordinating `FallbackChain[EmbeddingProvider]`.
- Formulated complete unit test specifications in `analysis_embeddings.md`.

## Artifact Index
- DISPATCH.md — incoming dispatch instructions and heartbeat checks
- BRIEFING.md — persistent working memory
- progress.md — liveness heartbeat and subtask tracking
- analysis_embeddings.md — detailed technical investigation and design
- handoff.md — self-contained handoff report (Hard handoff)
