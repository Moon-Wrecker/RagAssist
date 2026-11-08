# Handoff Report: Model Catalog & LLM Provider Platform Architecture

**Agent**: Milestone 1 Explorer 1 (Model Catalog & LLM Provider Architecture)  
**Date**: 2026-11-07T20:33:00Z  
**State Folder**: `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_1`  
**Target Path for Full Analysis**: `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_1\analysis_models.md`  

---

## 1. Observation

1. **Existing LLM Platform Ports**:
   - `src/ragassist/platform/llm/ports.py:9-26`:
     ```python
     @dataclass(frozen=True)
     class ModelPricing:
         input_cost_per_mtok: float = 0.0
         output_cost_per_mtok: float = 0.0

     @dataclass(frozen=True)
     class ModelCapabilities:
         supports_tools: bool = True
         supports_json_schema: bool = True
         supports_streaming: bool = True
         supports_logprobs: bool = False
         context_window: int = 128_000
         pricing: ModelPricing = ModelPricing()
     ```
     Observed that `ModelCapabilities` does not include `supports_vision: bool`, nor does it provide `tool_calling` or `json_mode` attribute aliases.
   - `src/ragassist/platform/llm/ports.py:30-52`:
     `ChatModelProvider` protocol defines `name`, `get_capabilities(model_name: str)`, and `build_chat_model(...)`. `PROJECT.md § 126` also specifies `get_chat_model(...)` and `get_pricing(...)`.

2. **Existing LLM Platform Adapters**:
   - `src/ragassist/platform/llm/adapters/openai_adapter.py:20-31`:
     Hardcodes pricing and capabilities using naive string matching:
     ```python
     pricing = ModelPricing(input_cost_per_mtok=2.50, output_cost_per_mtok=10.00)
     if "mini" in model_name.lower():
         pricing = ModelPricing(input_cost_per_mtok=0.15, output_cost_per_mtok=0.60)
     ```
   - `src/ragassist/platform/llm/adapters/anthropic_adapter.py:20-31`:
     Hardcodes pricing ($3.00/$15.00 vs $0.25/$1.25) using `if "haiku" in model_name.lower()`.
   - `src/ragassist/platform/llm/adapters/openrouter_adapter.py:20-28, 63-71`:
     `OpenRouterAdapter` and `OpenAICompatibleAdapter` hardcode fixed pricing ($0.80/$2.40 and $0.0/$0.0) and context windows (128,000 and 32,000).

3. **Application Settings Configuration**:
   - `src/ragassist/shared/config/settings.py:72-77`:
     ```python
     LLM_ROLE_GENERATOR_PRIMARY: str = "gen-default"
     LLM_ROLE_GENERATOR_FALLBACKS: str = "gen-openrouter-llama"
     LLM_ROLE_REWRITER_PRIMARY: str = "gen-default"
     LLM_ROLE_AGENT_PRIMARY: str = "gen-default"
     LLM_ROLE_JUDGE_PRIMARY: str = "gen-default"
     LLM_ROLE_DECIDER_FALLBACK: str = "gen-default"
     ```
     Observed that logical profile keys/aliases (`gen-default`, `gen-openrouter-llama`) are already referenced in configuration, but currently have no configuration file defining what models they map to.

4. **Shared Resilience & Registry Infrastructure**:
   - `src/ragassist/shared/registry.py:12-40`:
     `ProviderRegistry[T]` is already fully implemented, thread-safe, and provides `register()`, `create()`, `is_registered()`, and `available_providers()`.
   - `src/ragassist/shared/resilience.py:30-74`:
     `FallbackChain[T]` is already implemented with async `execute(operation, is_acceptable)`.

5. **Runtime Environment & Dependencies**:
   - `pyproject.toml:23-27`: `langchain>=0.3.3`, `langchain-core>=0.3.10`, `langchain-openai>=0.2.2`, `langchain-anthropic>=0.2.3`, `langchain-openrouter>=0.1.0`.
   - Shell verification: PyYAML 6.0.3 is installed in `.venv`.

---

## 2. Logic Chain

1. From **Observation 2**, the existing LLM adapters hardcode model pricing, token limits, and capabilities via ad-hoc string checks. This directly violates repository architectural rule **AGENTS.md § 2.1 ("No Hardcoded Models or Keys")**, which mandates that all model selections go through a provider registry and configuration files.
2. From **Observation 3**, `settings.py` references logical role profiles (`gen-default`, `gen-openrouter-llama`) for roles `generator`, `rewriter`, `agent`, `judge`, and `decider`, but no file exists to bind these aliases to concrete providers, pricing, or endpoints.
3. Therefore, an authoritative, validated declarative configuration file `config/models.yaml` must be created containing four top-level sections: `providers`, `models`, `aliases`, and `roles`.
4. From **Observation 1**, `ModelCapabilities` requires `supports_vision` to accurately represent multimodal vision models (such as GPT-4o and Claude 3.5 Sonnet), and property aliases (`tool_calling`, `json_mode`, `vision`) to align directly with YAML capability keys.
5. From **Observation 4**, `ProviderRegistry[T]` in `shared/registry.py` provides the exact generic contract needed to instantiate named adapters (`openai`, `anthropic`, `openrouter`, `openai_compatible`).
6. From **Observation 4**, `FallbackChain[T]` in `shared/resilience.py` provides the exact mechanism needed to wrap an ordered sequence of `BaseChatModel` instances so that failover across providers (e.g. OpenAI -> Anthropic -> OpenRouter) occurs automatically upon transient API errors or rate limits.
7. By introducing `ModelCatalog` to parse `config/models.yaml` via Pydantic v2 schemas and pairing it with an `LLMService` facade that manages `ProviderRegistry[ChatModelProvider]` and `FallbackChain[BaseChatModel]`, the system fulfills all requirements of Milestone 1 with clean separation of concerns and hexagonal layering.

---

## 3. Caveats

1. **Local LLM Endpoint Connectivity**:
   - The `openai_compatible` provider specifies `http://localhost:11434/v1` (Ollama default). In sandboxed environments or machines without a running Ollama daemon, unit tests must mock or skip actual network calls to this URL.
2. **API Keys in Test Environments**:
   - Adapters currently use dummy fallback strings (e.g. `"<redacted>"`) if environment variables are not set. Unit tests must not attempt live external API calls against real OpenAI or Anthropic endpoints.
3. **Embeddings & Deciders Scope**:
   - This investigation focused specifically on the LLM model catalog, provider registry, and chat model fallback chains. Embedding providers and System One Deciders (Jev, OpenAI Decisions, Semantic Router) will be wired into parallel registries following the same architectural pattern.

---

## 4. Conclusion

The model catalog and LLM provider architecture design is complete, verified, and documented in `d:\Coding\RagAssist-1\.agents\teamwork\explorer_m1_1\analysis_models.md`.

The implementer can execute this design through the following scoped steps:
1. Create `config/models.yaml` using the complete YAML structure defined in Section 3 of `analysis_models.md`.
2. Update `src/ragassist/platform/llm/ports.py` to add `supports_vision` and parity methods.
3. Add `MODELS_CONFIG_PATH: str = "config/models.yaml"` to `src/ragassist/shared/config/settings.py` and update `.env.example`.
4. Implement `catalog_models.py` and `catalog.py` under `src/ragassist/platform/llm/`.
5. Implement `LLMService` and `create_default_llm_registry()` in `src/ragassist/platform/llm/service.py`.
6. Refactor `OpenAIAdapter`, `AnthropicAdapter`, and `OpenRouterAdapter` to query `ModelCatalog`.
7. Add the comprehensive unit test suite in `tests/unit/test_model_catalog.py`.

---

## 5. Verification Method

To independently verify the architecture and subsequent implementation:

1. **Schema and File Verification**:
   - Check that `config/models.yaml` exists and adheres to the YAML structure in `analysis_models.md`.
   - Run Python validation:
     ```powershell
     $env:PYTHONPATH='src'; .venv\Scripts\python.exe -c "from ragassist.platform.llm.catalog import ModelCatalog; cat = ModelCatalog.load_from_yaml('config/models.yaml'); print('Catalog loaded:', len(cat._models), 'models')"
     ```

2. **Unit Test Suite Execution**:
   - Run the dedicated unit test suite:
     ```powershell
     $env:PYTHONPATH='src'; .venv\Scripts\python.exe -m pytest tests/unit/test_model_catalog.py -v
     ```
   - Invalidation condition: Any failure in parsing `models.yaml`, resolving aliases (`gen-default`, `fast-default`), constructing role fallback chains, or instantiating registered adapters.

3. **Static Analysis & Linting**:
   - Verify zero lint and typing regressions:
     ```powershell
     .venv\Scripts\ruff.exe check src/ragassist/platform/llm
     .venv\Scripts\mypy.exe src/ragassist/platform/llm
     ```
