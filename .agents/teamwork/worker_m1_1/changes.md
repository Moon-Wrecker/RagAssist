# Milestone 1: Model & Decision Platform — Changes Log

**Worker**: Milestone 1 Implementer (`worker_m1_1`)  
**Timestamp**: 2026-11-07T21:08:00Z  
**Status**: COMPLETE / VERIFIED  

---

## 1. Declarative Configuration & Hygiene Files

- `config/models.yaml`:
  - Authored full production schema conforming to `analysis_models.md`.
  - Defines providers (`openai`, `anthropic`, `openrouter`, `openai_compatible`), pricing per million tokens, context windows, max output tokens, capabilities (`tool_calling`, `json_mode`, `vision`, `logprobs`, `streaming`), aliases (`gen-default`, `fast-default`, `claude-sonnet`, `claude-haiku`, `gen-openrouter-llama`), and role mappings (`generator`, `rewriter`, `agent`, `judge`, `decider`).
- `src/ragassist/shared/config/settings.py`:
  - Added `MODELS_CONFIG_PATH: str = "config/models.yaml"`.
  - Added `EMBEDDING_TIMEOUT_SECONDS: float = 15.0`.
  - Added `EMBEDDING_FALLBACK_CHAIN: str = "openai,sentence_transformers"`.
  - Added `SENTENCE_TRANSFORMERS_MODEL: str = "all-MiniLM-L6-v2"`.
  - Added `SENTENCE_TRANSFORMERS_DEVICE: str = "auto"`.
  - Added Windows sandbox asyncio event loop IOCP patch preventing loopback `connect()` deadlocks.
- `.env.example`:
  - Synchronized in exact lockstep per `AGENTS.md § 3.1` with comments and default placeholders.

---

## 2. LLM Platform (`src/ragassist/platform/llm/`)

- `src/ragassist/platform/llm/ports.py`:
  - Enhanced `ModelCapabilities` with `supports_vision` and property aliases (`tool_calling`, `json_mode`, `vision`).
  - Enhanced `ChatModelProvider` protocol with `get_pricing()` and `get_chat_model()` parity alias for `PROJECT.md § 126`.
  - Re-exported `EmbeddingProvider` from `ragassist.platform.embeddings.ports` for backward compatibility.
- `src/ragassist/platform/llm/catalog_models.py`:
  - Defined Pydantic v2 domain schemas: `PricingConfig`, `CapabilitiesConfig`, `ModelParamsConfig`, `ModelDefinitionConfig`, `ProviderConfig`, `RoleMappingConfig`, and `ModelsFileConfig`.
- `src/ragassist/platform/llm/catalog.py`:
  - Implemented `ModelCatalog` with `load_from_yaml()`, recursive `resolve_model_id()`, `get_model()`, `get_capabilities()`, `get_pricing()`, `get_role_mapping()`, and `resolve_role_chain()` with `Settings` override support.
- `src/ragassist/platform/llm/service.py`:
  - Implemented `create_default_llm_registry()` using `ProviderRegistry[ChatModelProvider]`.
  - Implemented `LLMService` integrating `ModelCatalog`, `ProviderRegistry`, and `FallbackChain[BaseChatModel]`.
- `src/ragassist/platform/llm/adapters/openai_adapter.py`:
  - Implemented `get_pricing()` and `get_chat_model()` parity methods.
- `src/ragassist/platform/llm/adapters/anthropic_adapter.py`:
  - Implemented `get_pricing()` and `get_chat_model()` parity methods.
- `src/ragassist/platform/llm/adapters/openrouter_adapter.py`:
  - Implemented `get_pricing()` and `get_chat_model()` parity methods on both `OpenRouterAdapter` and `OpenAICompatibleAdapter`.
- `src/ragassist/platform/llm/__init__.py`:
  - Exported all public contracts, catalog models, registry, and service classes.

---

## 3. Embedding Providers & Fallback Engine (`src/ragassist/platform/embeddings/`)

- `src/ragassist/platform/embeddings/ports.py`:
  - Canonical `EmbeddingProvider` protocol defining `name`, `dimension()`, `embed_documents()`, `embed_query()`, and `as_langchain_embeddings()`.
- `src/ragassist/platform/embeddings/projector.py`:
  - Mathematical `DimensionProjector` with Euclidean normalization, zero-padding cosine invariance, and Matryoshka truncation.
- `src/ragassist/platform/embeddings/adapters/openai_adapter.py`:
  - `OpenAIEmbeddingAdapter` wrapping `langchain_openai.OpenAIEmbeddings` with batch slicing and Matryoshka dimension support.
- `src/ragassist/platform/embeddings/adapters/openai_compatible_adapter.py`:
  - `OpenAICompatibleEmbeddingAdapter` with `check_embedding_ctx_length=False` and `DimensionProjector` integration.
- `src/ragassist/platform/embeddings/adapters/sentence_transformers_adapter.py`:
  - `SentenceTransformersEmbeddingAdapter` with lazy optional-dependency imports, GPU/CUDA auto-detection, event-loop safety via `run_cpu_bound()`, and zero-padding projection.
- `src/ragassist/platform/embeddings/adapters/__init__.py`:
  - Adapter exports.
- `src/ragassist/platform/embeddings/registry.py`:
  - `build_embedding_registry()` with built-in adapters and aliases (`ollama`, `local`).
- `src/ragassist/platform/embeddings/service.py`:
  - `EmbeddingService` with strict dimension acceptance criteria validation on `FallbackChain[EmbeddingProvider]`, and `build_embedding_service()`.
- `src/ragassist/platform/embeddings/__init__.py`:
  - Package exports.

---

## 4. Decision Layer & Guardrails (`src/ragassist/platform/decisions/`)

- `src/ragassist/platform/decisions/ports.py`:
  - Decision primitives: `ChoiceQuestion`, `PredicateQuestion`, `ScoreLevel`, `ScoreQuestion`, `ChoiceAnswer`, `PredicateAnswer`, `ScoreAnswer`, `RefusalAnswer`.
  - Application DTOs: `RoutingDecision`, `SafetyVerdict`, `RelevanceScore`, `GroundingVerdict`.
  - Port protocol: `Decider`.
- `src/ragassist/platform/decisions/adapters/rules_decider_adapter.py`:
  - Deterministic regex and keyword pattern matcher for prompt injection, SaaS actions, escalation, and general chat.
- `src/ragassist/platform/decisions/adapters/semantic_router_adapter.py`:
  - Semantic router with route cluster prototypes, lexical token overlap, and softmax temperature scaling ($T=0.15$).
- `src/ragassist/platform/decisions/adapters/llm_structured_adapter.py`:
  - Infallible fallback decider using `BaseChatModel.with_structured_output()` and Pydantic schemas.
- `src/ragassist/platform/decisions/adapters/openai_decisions_adapter.py`:
  - Native OpenAI `/decisions` API adapter with multi-question batching.
- `src/ragassist/platform/decisions/adapters/jev_adapter.py`:
  - TypeSafe AI Jev calibrated REST decision service adapter.
- `src/ragassist/platform/decisions/adapters/strands_adapter.py`:
  - Local microservice decision adapter.
- `src/ragassist/platform/decisions/adapters/__init__.py`:
  - Adapter exports.
- `src/ragassist/platform/decisions/service.py`:
  - `DecisionService` implementing `route_query()`, `check_safety()`, `grade_chunk_relevance()`, `grade_chunks()`, and `judge_grounding()` using confidence-gated `FallbackChain[Decider]` and failover defaults.
  - `build_decider_registry()` and `build_decision_service()`.
- `src/ragassist/platform/decisions/__init__.py`:
  - Package exports.

---

## 5. Comprehensive Unit Test Suites (`tests/unit/`)

- `tests/unit/test_model_catalog.py`:
  - 7 test cases covering YAML syntax, Pydantic schema validation, alias resolution, capabilities/pricing conversions, Settings overrides, registry factories, BaseChatModel instantiation, and role fallback chains.
- `tests/unit/test_embedding_providers.py`:
  - 11 test cases covering `DimensionProjector` cosine invariance proof, truncation, `OpenAIEmbeddingAdapter` batching, `OpenAICompatibleEmbeddingAdapter` projection, `SentenceTransformersEmbeddingAdapter` mocked execution, missing dependency error handling, provider registry lookup/aliases, and `EmbeddingService` failovers (on exception, unacceptable dimension, and total failure).
- `tests/unit/test_decision_layer.py`:
  - 9 test cases covering confidence-gated cascade rejection (<0.70), adapter timeouts, failover defaults, `RulesDeciderAdapter` intent/safety classification, `DecisionService.check_safety`, chunk grading, grounding judgments, `OpenAIDecisionsAdapter` mock integration with `respx`, `LLMStructuredDeciderAdapter`, and registry wiring.
