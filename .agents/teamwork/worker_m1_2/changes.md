# Changes Summary — Milestone 1 (Model & Decision Platform)

## Overview
Milestone 1 delivers the multi-provider LLM catalog, embedding dimension projector and provider registry, and the fast decision layer with confidence-gated fallback cascades.

## Inventory of Verified Files

### 1. Configuration & Catalogs
- `config/models.yaml`:
  - Declarative schema (version 1.0) defining providers (`openai`, `anthropic`, `openrouter`, `openai_compatible`).
  - Model definitions with context windows, max output tokens, token pricing (USD per Mtok), capabilities (`tool_calling`, `json_mode`, `vision`, `streaming`, `logprobs`), and default parameters.
  - Role definitions with primary and ordered fallback chains: `generator`, `rewriter`, `agent`, `judge`, `decider`.
  - Embedding model catalog: `text-embedding-3-small`, `text-embedding-3-large`, `all-MiniLM-L6-v2`, `bge-base-en-v1.5`, `nomic-embed-text`.

### 2. Platform: LLM (`src/ragassist/platform/llm/`)
- `ports.py`:
  - `ChatModelProvider` protocol (`get_capabilities`, `get_pricing`, `build_chat_model`, `get_chat_model`).
  - `ModelCapabilities` and `ModelPricing` domain dataclasses.
  - Re-export of `EmbeddingProvider` for interface parity.
- `catalog_models.py`:
  - Pydantic V2 models validating `models.yaml`: `ModelsFileConfig`, `ProviderCatalogEntry`, `ModelCatalogEntry`, `RoleConfig`, `PricingConfig`, `CapabilitiesConfig`.
- `catalog.py`:
  - `ModelCatalog` singleton loader with recursive alias resolution, provider lookup, capabilities/pricing mapping, and role fallback extraction.
- `service.py`:
  - `LLMService` orchestrating model resolution, fallback chain execution, and LangChain model instantiation via `ProviderRegistry`.
- `adapters/`:
  - `openai_adapter.py`: ChatOpenAI adapter.
  - `anthropic_adapter.py`: ChatAnthropic adapter.
  - `openrouter_adapter.py`: OpenRouter OpenAI-compatible adapter with custom HTTP headers.
  - `openai_compatible_adapter.py`: Local / self-hosted endpoint adapter.

### 3. Platform: Embeddings (`src/ragassist/platform/embeddings/`)
- `ports.py`:
  - `EmbeddingProvider` runtime checkable protocol (`embed_documents`, `embed_query`, `dimension`).
- `projector.py`:
  - `DimensionProjector` ensuring fixed dimension output (e.g., 1536 for pgvector) across disparate models.
  - Uses zero-padding (mathematically cosine-similarity invariant) or truncation, followed by L2 normalization.
- `registry.py`:
  - Generic `ProviderRegistry` for embedding adapters (`openai`, `sentence_transformers`, `openai_compatible`).
- `service.py`:
  - `EmbeddingService` coordinating provider execution through `FallbackChain` and dimension alignment via `DimensionProjector`.
- `adapters/`:
  - `openai_adapter.py`: OpenAI embeddings API.
  - `openai_compatible_adapter.py`: Generic OpenAI-compatible embedding API.
  - `sentence_transformers_adapter.py`: Local HuggingFace SentenceTransformer with async execution via bounded thread pool.

### 4. Platform: Decisions (`src/ragassist/platform/decisions/`)
- `ports.py`:
  - Decision DTOs: `RoutingDecision`, `SafetyVerdict`, `RelevanceScore`, `GroundingVerdict`.
  - Structured input/output models: `ChoiceQuestion`, `ChoiceAnswer`, `PredicateQuestion`, `PredicateAnswer`, `ScoreQuestion`, `ScoreAnswer`.
  - `Decider` runtime checkable protocol.
- `adapters/`:
  - `jev_adapter.py`: Calibrated confidence decision adapter.
  - `openai_decisions_adapter.py`: OpenAI structured output decider.
  - `strands_adapter.py`: Local small models / Strands adapter.
  - `semantic_router_adapter.py`: Embedding cosine-distance semantic router.
  - `llm_structured_adapter.py`: Generic LLM structured output decider.
  - `rules_decider_adapter.py`: Fast deterministic rule-based decider.
- `service.py`:
  - `DecisionService` providing `route_intent`, `guard_input`, `grade_chunk_relevance`, and `judge_grounding` with confidence-gated fallback cascades.

### 5. Shared Kernel & Configuration
- `src/ragassist/shared/config/settings.py` & `.env.example`:
  - Synchronized configurations for model paths, default roles, decider thresholds, embedding dimension, provider credentials.

### 6. Unit Tests (`tests/unit/`)
- `tests/unit/test_model_catalog.py`: YAML schema validation, alias resolution, capability/pricing conversion, LLMService fallback resolution (7 passed).
- `tests/unit/test_embedding_providers.py`: DimensionProjector cosine invariance, zero-padding, truncation, OpenAI/compatible/ST adapters, fallback chain (11 passed).
- `tests/unit/test_decision_layer.py`: Rules decider, semantic router, LLM structured decider, DecisionService routing, safety guards, relevance grading, grounding judgment, fallback cascades (9 passed).
- `tests/unit/test_shared_kernel.py`: Domain types, JWT principal encoding/decoding, FallbackChain execution (3 passed).
