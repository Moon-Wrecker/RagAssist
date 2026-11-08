# Architecture Analysis & Implementation Plan: Model Catalog & LLM Provider Platform

**Author**: Milestone 1 Explorer 1 (Model Catalog & LLM Provider Architecture)  
**Date**: 2026-11-07  
**Status**: APPROVED DESIGN / READY FOR IMPLEMENTATION  
**Target Milestone**: Milestone 1: Model & Decision Platform  

---

## 1. Executive Summary

RagAssist requires a production-grade, multi-provider model routing and execution subsystem. In accordance with **AGENTS.md § 2 ("Configuration & Provider Abstraction Rules")**, all LLM selections, pricing records, capability definitions, and role assignments must be driven centrally by declarative configuration (`config/models.yaml`) and runtime environment overrides—eliminating hardcoded model names and static pricing scattered across adapter classes.

This document delivers:
1. **Gap Analysis** of current LLM platform ports and adapters in `src/ragassist/platform/llm/`.
2. **Declarative Specification and Production Schema** for `config/models.yaml`.
3. **Pydantic Data Contracts** for parsing, validating, and managing the model catalog (`ModelCatalog`).
4. **Provider Registry & LLM Manager Architecture** integrating `ProviderRegistry[ChatModelProvider]`, `FallbackChain[BaseChatModel]`, and `Settings`.
5. **Concrete Implementation Signatures** and step-by-step refactoring guidelines for existing adapters.
6. **Comprehensive Unit Test Specifications** verifying schema compliance, catalog resolution, provider factories, and failover chains.

---

## 2. Analysis of Existing Codebase

### 2.1 Current Artifacts Examined

| File Path | Role | Key Findings & Deficiencies |
|---|---|---|
| `src/ragassist/platform/llm/ports.py` | Abstract protocols and DTOs | Defines `ModelPricing`, `ModelCapabilities`, `ChatModelProvider`, and `EmbeddingProvider`. Lacks `supports_vision` in `ModelCapabilities`. `ChatModelProvider` protocol defines `build_chat_model` while `PROJECT.md § 126` also references `get_chat_model` and `get_pricing`. |
| `src/ragassist/platform/llm/adapters/openai_adapter.py` | OpenAI adapter | Hardcodes pricing ($2.50/$10.00 vs $0.15/$0.60) via substring `if "mini" in model_name`. Lacks dynamic catalog lookup. |
| `src/ragassist/platform/llm/adapters/anthropic_adapter.py` | Anthropic Claude adapter | Hardcodes pricing ($3.00/$15.00 vs $0.25/$1.25) via substring `if "haiku" in model_name`. Hardcodes max output sample tokens to 4096. |
| `src/ragassist/platform/llm/adapters/openrouter_adapter.py` | OpenRouter & OpenAI-Compatible adapters | Contains two classes (`OpenRouterAdapter` and `OpenAICompatibleAdapter`). Hardcodes static capabilities and dummy pricing ($0.80/$2.40). |
| `src/ragassist/shared/registry.py` | Generic provider registry | Clean, thread-safe `ProviderRegistry[T]` mapping normalized strings to factory callables. Perfectly suited for LLM provider registration. |
| `src/ragassist/shared/resilience.py` | FallbackChain & thread executor | `FallbackChain[T]` executes operations with automatic failover and optional acceptance criteria (`is_acceptable`). Ready for chaining chat models. |
| `src/ragassist/shared/config/settings.py` | Central application settings | Declares `LLM_ROLE_GENERATOR_PRIMARY="gen-default"`, `LLM_ROLE_GENERATOR_FALLBACKS="gen-openrouter-llama"`, `LLM_ROLE_REWRITER_PRIMARY`, `LLM_ROLE_AGENT_PRIMARY`, `LLM_ROLE_JUDGE_PRIMARY`, `LLM_ROLE_DECIDER_FALLBACK`. Needs explicit `MODELS_CONFIG_PATH="config/models.yaml"`. |

### 2.2 Critical Design Findings

1. **Elimination of Hardcoded Metadata in Adapters**:
   Adapters must no longer guess pricing or context windows from model name strings. The `ModelCatalog` will act as the single source of truth. When an adapter's `get_capabilities()` or `get_pricing()` is invoked, it delegates to the catalog (or receives a pre-resolved `ModelDefinition`).

2. **Role Aliases vs Model Identifiers**:
   Existing `settings.py` references aliases such as `"gen-default"` and `"gen-openrouter-llama"`. `config/models.yaml` must provide an explicit `aliases` map or alias resolution so that `"gen-default"` resolves to `gpt-4o` (or `gpt-4o-mini`) and `"gen-openrouter-llama"` resolves to `openrouter/meta-llama/llama-3.1-70b-instruct`.

3. **Fallback Chains at BaseChatModel Level**:
   In LangGraph workflows and service layers, nodes need a resilient chat model invocation. By wrapping a list of `BaseChatModel` instances (or client wrappers) in `FallbackChain`, an agent can execute `chain.execute(lambda m: m.ainvoke(messages))` and gracefully fail over on rate limits (HTTP 429), timeouts (HTTP 504), or provider outages.

---

## 3. Specification & Schema for `config/models.yaml`

### 3.1 Requirements Matrix

The schema must capture:
- **Providers**: Credentials source, base URL, default headers, request timeouts.
- **Models**:
  - Unique model identifier / key.
  - Provider identifier (`openai`, `anthropic`, `openrouter`, `openai_compatible`).
  - Underlying API model identifier (e.g. `gpt-4o`, `claude-3-5-sonnet-20241022`).
  - Context window (tokens) and maximum output tokens.
  - Pricing in USD per million tokens: `input_cost_per_mtok`, `output_cost_per_mtok`.
  - Capabilities: `tool_calling`, `json_mode`, `vision`, `logprobs`, `streaming`.
  - Default inference parameters (`temperature`, `timeout_seconds`).
- **Role Mappings**:
  - `generator`: Synthesis and final RAG response generation.
  - `rewriter`: Query rewriting, query expansion, HyDE generation.
  - `agent`: Core conversational agent with tool calling (`modules/assistant`).
  - `judge`: Post-generation grounding and hallucination evaluation.
  - `decider`: LLM fallback for System One decisions (when semantic router / Jev is unavailable).
- **Aliases**: Canonical aliases mapping logical keys (e.g. `gen-default`, `fast-default`) to specific model entries.

### 3.2 Canonical YAML Content (`config/models.yaml`)

```yaml
# ==============================================================================
# RagAssist Model Catalog & Role Configuration
# ==============================================================================
# Single source of truth for LLM providers, model capabilities, pricing, and role assignments.
# Synchronized with src/ragassist/shared/config/settings.py and AGENTS.md § 2.

version: "1.0"

providers:
  openai:
    adapter: openai
    api_key_env: OPENAI_API_KEY
    timeout_seconds: 30.0

  anthropic:
    adapter: anthropic
    api_key_env: ANTHROPIC_API_KEY
    timeout_seconds: 30.0

  openrouter:
    adapter: openrouter
    api_key_env: OPENROUTER_API_KEY
    base_url: "https://openrouter.ai/api/v1"
    default_headers:
      HTTP-Referer: "https://github.com/ragassist/ragassist"
      X-Title: "RagAssist"
    timeout_seconds: 45.0

  openai_compatible:
    adapter: openai_compatible
    api_key_env: OPENAI_COMPATIBLE_API_KEY
    base_url_env: OPENAI_COMPATIBLE_BASE_URL
    timeout_seconds: 60.0

models:
  # --- OpenAI Models ---
  gpt-4o:
    provider: openai
    model_name: "gpt-4o"
    context_window: 128000
    max_output_tokens: 4096
    pricing:
      input_cost_per_mtok: 2.50
      output_cost_per_mtok: 10.00
    capabilities:
      tool_calling: true
      json_mode: true
      vision: true
      logprobs: true
      streaming: true
    default_params:
      temperature: 0.1

  gpt-4o-mini:
    provider: openai
    model_name: "gpt-4o-mini"
    context_window: 128000
    max_output_tokens: 16384
    pricing:
      input_cost_per_mtok: 0.15
      output_cost_per_mtok: 0.60
    capabilities:
      tool_calling: true
      json_mode: true
      vision: true
      logprobs: true
      streaming: true
    default_params:
      temperature: 0.0

  # --- Anthropic Models ---
  claude-3-5-sonnet:
    provider: anthropic
    model_name: "claude-3-5-sonnet-20241022"
    context_window: 200000
    max_output_tokens: 8192
    pricing:
      input_cost_per_mtok: 3.00
      output_cost_per_mtok: 15.00
    capabilities:
      tool_calling: true
      json_mode: true
      vision: true
      logprobs: false
      streaming: true
    default_params:
      temperature: 0.1

  claude-3-5-haiku:
    provider: anthropic
    model_name: "claude-3-5-haiku-20241022"
    context_window: 200000
    max_output_tokens: 8192
    pricing:
      input_cost_per_mtok: 0.80
      output_cost_per_mtok: 4.00
    capabilities:
      tool_calling: true
      json_mode: true
      vision: false
      logprobs: false
      streaming: true
    default_params:
      temperature: 0.0

  # --- OpenRouter Routed Models ---
  openrouter-llama-3.1-70b:
    provider: openrouter
    model_name: "meta-llama/llama-3.1-70b-instruct"
    context_window: 131072
    max_output_tokens: 4096
    pricing:
      input_cost_per_mtok: 0.40
      output_cost_per_mtok: 0.40
    capabilities:
      tool_calling: true
      json_mode: true
      vision: false
      logprobs: false
      streaming: true
    default_params:
      temperature: 0.1

  openrouter-mistral-large:
    provider: openrouter
    model_name: "mistralai/mistral-large-2407"
    context_window: 128000
    max_output_tokens: 4096
    pricing:
      input_cost_per_mtok: 2.00
      output_cost_per_mtok: 6.00
    capabilities:
      tool_calling: true
      json_mode: true
      vision: false
      logprobs: false
      streaming: true
    default_params:
      temperature: 0.1

  # --- Local / OpenAI-Compatible (Ollama / vLLM / Groq) ---
  local-llama-3.1-8b:
    provider: openai_compatible
    model_name: "llama3.1:8b"
    context_window: 32768
    max_output_tokens: 4096
    pricing:
      input_cost_per_mtok: 0.0
      output_cost_per_mtok: 0.0
    capabilities:
      tool_calling: true
      json_mode: true
      vision: false
      logprobs: false
      streaming: true
    default_params:
      temperature: 0.0

aliases:
  gen-default: "gpt-4o"
  gen-openrouter-llama: "openrouter-llama-3.1-70b"
  fast-default: "gpt-4o-mini"
  claude-sonnet: "claude-3-5-sonnet"
  claude-haiku: "claude-3-5-haiku"

roles:
  generator:
    primary: "gen-default"
    fallbacks:
      - "claude-3-5-sonnet"
      - "gen-openrouter-llama"
    temperature: 0.1
    max_tokens: 2048

  rewriter:
    primary: "fast-default"
    fallbacks:
      - "claude-3-5-haiku"
    temperature: 0.0
    max_tokens: 512

  agent:
    primary: "gen-default"
    fallbacks:
      - "claude-3-5-sonnet"
    temperature: 0.0
    max_tokens: 4096

  judge:
    primary: "fast-default"
    fallbacks:
      - "claude-3-5-haiku"
    temperature: 0.0
    max_tokens: 1024

  decider:
    primary: "fast-default"
    fallbacks:
      - "claude-3-5-haiku"
    temperature: 0.0
    max_tokens: 256
```

---

## 4. Pydantic Domain & Configuration Models

To validate `config/models.yaml` with strict typing and schema safety, we define Pydantic v2 configuration schemas in `src/ragassist/platform/llm/catalog_models.py` (or directly within `catalog.py`).

### 4.1 Schema Definitions

```python
"""Pydantic schemas for models.yaml parsing and catalog data structures."""

from pydantic import BaseModel, Field, ConfigDict
from ragassist.platform.llm.ports import ModelCapabilities, ModelPricing


class PricingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_cost_per_mtok: float = Field(default=0.0, ge=0.0)
    output_cost_per_mtok: float = Field(default=0.0, ge=0.0)

    def to_domain(self) -> ModelPricing:
        return ModelPricing(
            input_cost_per_mtok=self.input_cost_per_mtok,
            output_cost_per_mtok=self.output_cost_per_mtok,
        )


class CapabilitiesConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_calling: bool = Field(default=True)
    json_mode: bool = Field(default=True)
    vision: bool = Field(default=False)
    logprobs: bool = Field(default=False)
    streaming: bool = Field(default=True)

    def to_domain(self, context_window: int, pricing: ModelPricing) -> ModelCapabilities:
        return ModelCapabilities(
            supports_tools=self.tool_calling,
            supports_json_schema=self.json_mode,
            supports_streaming=self.streaming,
            supports_logprobs=self.logprobs,
            supports_vision=self.vision,
            context_window=context_window,
            pricing=pricing,
        )


class ModelParamsConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: float | None = Field(default=None, gt=0.0)


class ModelDefinitionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model_name: str
    context_window: int = Field(default=128000, gt=0)
    max_output_tokens: int = Field(default=4096, gt=0)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    default_params: ModelParamsConfig = Field(default_factory=ModelParamsConfig)


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    adapter: str
    api_key_env: str = ""
    base_url: str | None = None
    base_url_env: str | None = None
    default_headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=30.0, gt=0.0)


class RoleMappingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    primary: str
    fallbacks: list[str] = Field(default_factory=list)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)


class ModelsFileConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: str = "1.0"
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelDefinitionConfig]
    aliases: dict[str, str] = Field(default_factory=dict)
    roles: dict[str, RoleMappingConfig]
```

---

## 5. Model Catalog & Provider Registry Architecture

### 5.1 Architecture Diagram

```
 ┌──────────────────────┐
 │  config/models.yaml  │
 └──────────┬───────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────────┐
 │                      ModelCatalog                       │
 │  - Validates YAML with ModelsFileConfig                 │
 │  - Resolves aliases (gen-default -> gpt-4o)             │
 │  - Returns ModelCapabilities & ModelPricing             │
 │  - Resolves Role Mappings (primary + fallback list)     │
 └──────────┬──────────────────────────────────────────────┘
            │
            ├─────────────────────────────────────────────┐
            ▼                                             ▼
 ┌──────────────────────────────────────┐     ┌──────────────────────────────────────┐
 │ ProviderRegistry[ChatModelProvider]  │     │               Settings               │
 │  - "openai"    -> OpenAIAdapter      │     │  - LLM_ROLE_GENERATOR_PRIMARY        │
 │  - "anthropic" -> AnthropicAdapter   │     │  - LLM_ROLE_GENERATOR_FALLBACKS      │
 │  - "openrouter"-> OpenRouterAdapter  │     │  - API Keys / Endpoints              │
 │  - "openai_compatible" -> Adapter    │     └───────────────────┬──────────────────┘
 └──────────────────┬───────────────────┘                         │
                    │                                             │
                    ▼                                             │
 ┌────────────────────────────────────────────────────────────────┴──┐
 │                            LLMService                             │
 │  - get_chat_model(model_or_alias, **kwargs) -> BaseChatModel      │
 │  - get_role_chat_model(role, **kwargs)      -> BaseChatModel      │
 │  - get_role_fallback_chain(role, **kwargs)  -> FallbackChain      │
 └──────────────────────────────────┬────────────────────────────────┘
                                    │
               ┌────────────────────┼────────────────────┐
               ▼                    ▼                    ▼
       modules/assistant     modules/knowledge   modules/retrieval
         (LangGraph)            (Rewriter)            (Judge)
```

### 5.2 ModelCatalog Implementation Design

The `ModelCatalog` (`src/ragassist/platform/llm/catalog.py`) handles YAML parsing, caching, alias resolution, and role extraction:

```python
"""Model catalog loader and capability resolver."""

from pathlib import Path
from typing import Any
import yaml
from ragassist.platform.llm.catalog_models import ModelsFileConfig, ModelDefinitionConfig, RoleMappingConfig
from ragassist.platform.llm.ports import ModelCapabilities, ModelPricing
from ragassist.shared.config.settings import Settings, get_settings


class ModelCatalog:
    """Thread-safe catalog loaded from config/models.yaml."""

    def __init__(self, config: ModelsFileConfig) -> None:
        self._config = config
        self._models = config.models
        self._aliases = config.aliases
        self._roles = config.roles
        self._providers = config.providers

    @classmethod
    def load_from_yaml(cls, path: str | Path = "config/models.yaml") -> "ModelCatalog":
        """Load and parse models configuration from YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Model catalog config file not found: {file_path.resolve()}")
        
        with file_path.open("r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
            
        config = ModelsFileConfig.model_validate(raw_data)
        return cls(config)

    def resolve_model_id(self, key_or_alias: str) -> str:
        """Resolve alias to canonical model key, or return key if already canonical."""
        target = key_or_alias.strip()
        while target in self._aliases:
            target = self._aliases[target]
        if target not in self._models:
            available = ", ".join(sorted(list(self._models.keys()) + list(self._aliases.keys())))
            raise KeyError(f"Unknown model or alias '{key_or_alias}'. Available: [{available}]")
        return target

    def get_model(self, key_or_alias: str) -> ModelDefinitionConfig:
        """Get canonical model definition."""
        canonical_id = self.resolve_model_id(key_or_alias)
        return self._models[canonical_id]

    def get_capabilities(self, key_or_alias: str) -> ModelCapabilities:
        """Get domain ModelCapabilities for a model."""
        model = self.get_model(key_or_alias)
        pricing = model.pricing.to_domain()
        return model.capabilities.to_domain(
            context_window=model.context_window,
            pricing=pricing,
        )

    def get_pricing(self, key_or_alias: str) -> ModelPricing:
        """Get domain ModelPricing for a model."""
        model = self.get_model(key_or_alias)
        return model.pricing.to_domain()

    def get_role_mapping(self, role: str) -> RoleMappingConfig:
        """Retrieve raw role configuration."""
        normalized_role = role.strip().lower()
        if normalized_role not in self._roles:
            available = ", ".join(sorted(self._roles.keys()))
            raise KeyError(f"Unknown role '{role}'. Defined roles: [{available}]")
        return self._roles[normalized_role]

    def resolve_role_chain(
        self,
        role: str,
        settings: Settings | None = None,
    ) -> list[str]:
        """Resolve ordered list of canonical model IDs for a role, with Settings override support."""
        settings = settings or get_settings()
        normalized_role = role.strip().lower()

        # Check environment overrides from Settings
        primary_override: str | None = None
        fallbacks_override: list[str] | None = None

        if normalized_role == "generator":
            primary_override = settings.LLM_ROLE_GENERATOR_PRIMARY
            if settings.LLM_ROLE_GENERATOR_FALLBACKS:
                fallbacks_override = [
                    f.strip() for f in settings.LLM_ROLE_GENERATOR_FALLBACKS.split(",") if f.strip()
                ]
        elif normalized_role == "rewriter":
            primary_override = settings.LLM_ROLE_REWRITER_PRIMARY
        elif normalized_role == "agent":
            primary_override = settings.LLM_ROLE_AGENT_PRIMARY
        elif normalized_role == "judge":
            primary_override = settings.LLM_ROLE_JUDGE_PRIMARY
        elif normalized_role == "decider":
            primary_override = settings.LLM_ROLE_DECIDER_FALLBACK

        # Base config from YAML
        role_cfg = self.get_role_mapping(normalized_role)
        primary = primary_override or role_cfg.primary
        fallbacks = fallbacks_override if fallbacks_override is not None else role_cfg.fallbacks

        raw_chain = [primary, *fallbacks]
        # Resolve all aliases to canonical IDs and deduplicate preserving order
        resolved_chain: list[str] = []
        for item in raw_chain:
            canonical = self.resolve_model_id(item)
            if canonical not in resolved_chain:
                resolved_chain.append(canonical)

        return resolved_chain
```

### 5.3 Provider Registry & Factory Wiring

We use `ProviderRegistry[ChatModelProvider]` from `src/ragassist/shared/registry.py`:

```python
"""LLM Provider Registry factory and built-in adapter registration."""

from ragassist.platform.llm.ports import ChatModelProvider
from ragassist.platform.llm.adapters.openai_adapter import OpenAIAdapter
from ragassist.platform.llm.adapters.anthropic_adapter import AnthropicAdapter
from ragassist.platform.llm.adapters.openrouter_adapter import OpenRouterAdapter, OpenAICompatibleAdapter
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.registry import ProviderRegistry


def create_default_llm_registry(settings: Settings | None = None) -> ProviderRegistry[ChatModelProvider]:
    """Create and populate the default LLM ChatModelProvider registry."""
    active_settings = settings or get_settings()
    registry = ProviderRegistry[ChatModelProvider]("llm_chat_provider")

    registry.register("openai", lambda: OpenAIAdapter(settings=active_settings))
    registry.register("anthropic", lambda: AnthropicAdapter(settings=active_settings))
    registry.register("openrouter", lambda: OpenRouterAdapter(settings=active_settings))
    registry.register("openai_compatible", lambda: OpenAICompatibleAdapter(settings=active_settings))

    return registry
```

### 5.4 LLM Service / Facade Architecture

The `LLMService` brings together `ModelCatalog`, `ProviderRegistry[ChatModelProvider]`, and `FallbackChain`:

```python
"""High-level LLM Service orchestrating model instantiation and fallback chains."""

from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from ragassist.platform.llm.catalog import ModelCatalog
from ragassist.platform.llm.ports import ChatModelProvider, ModelCapabilities, ModelPricing
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.registry import ProviderRegistry
from ragassist.shared.resilience import FallbackChain


class LLMService:
    """Service facade for constructing BaseChatModel instances and resilient FallbackChains."""

    def __init__(
        self,
        catalog: ModelCatalog,
        registry: ProviderRegistry[ChatModelProvider],
        settings: Settings | None = None,
    ) -> None:
        self.catalog = catalog
        self.registry = registry
        self.settings = settings or get_settings()
        self._provider_cache: dict[str, ChatModelProvider] = {}

    def _get_provider_adapter(self, provider_name: str) -> ChatModelProvider:
        normalized = provider_name.strip().lower()
        if normalized not in self._provider_cache:
            self._provider_cache[normalized] = self.registry.create(normalized)
        return self._provider_cache[normalized]

    def get_capabilities(self, model_or_alias: str) -> ModelCapabilities:
        """Inspect capabilities from catalog."""
        return self.catalog.get_capabilities(model_or_alias)

    def get_pricing(self, model_or_alias: str) -> ModelPricing:
        """Inspect token pricing from catalog."""
        return self.catalog.get_pricing(model_or_alias)

    def get_chat_model(
        self,
        model_or_alias: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        streaming: bool = True,
        **extra_kwargs: Any,
    ) -> BaseChatModel:
        """Instantiate a BaseChatModel from a model ID or alias."""
        model_def = self.catalog.get_model(model_or_alias)
        adapter = self._get_provider_adapter(model_def.provider)

        temp = temperature if temperature is not None else model_def.default_params.temperature
        tokens = max_tokens if max_tokens is not None else model_def.max_output_tokens

        return adapter.build_chat_model(
            model_name=model_def.model_name,
            temperature=temp,
            max_tokens=tokens,
            streaming=streaming,
            **extra_kwargs,
        )

    def get_role_chat_model(
        self,
        role: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        streaming: bool = True,
        **extra_kwargs: Any,
    ) -> BaseChatModel:
        """Instantiate the primary chat model for a role."""
        chain = self.catalog.resolve_role_chain(role, settings=self.settings)
        primary_model = chain[0]
        return self.get_chat_model(
            primary_model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=streaming,
            **extra_kwargs,
        )

    def get_role_fallback_chain(
        self,
        role: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        streaming: bool = True,
        **extra_kwargs: Any,
    ) -> FallbackChain[BaseChatModel]:
        """Construct an ordered FallbackChain of BaseChatModel instances for a role."""
        model_ids = self.catalog.resolve_role_chain(role, settings=self.settings)
        models: list[BaseChatModel] = []

        for mid in model_ids:
            model_instance = self.get_chat_model(
                mid,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                **extra_kwargs,
            )
            # Annotate model with identifier for structured logging
            setattr(model_instance, "name", mid)
            models.append(model_instance)

        return FallbackChain[BaseChatModel](name=f"role_chain_{role}", members=models)
```

---

## 6. Adapter Refactoring & Port Harmonization

### 6.1 Enhancing `ports.py`

Update `ModelCapabilities` in `src/ragassist/platform/llm/ports.py` to add `supports_vision` and property aliases for ergonomic access:

```python
@dataclass(frozen=True)
class ModelCapabilities:
    """Capabilities supported by a specific model or endpoint."""

    supports_tools: bool = True
    supports_json_schema: bool = True
    supports_streaming: bool = True
    supports_logprobs: bool = False
    supports_vision: bool = False
    context_window: int = 128_000
    pricing: ModelPricing = ModelPricing()

    @property
    def tool_calling(self) -> bool:
        return self.supports_tools

    @property
    def json_mode(self) -> bool:
        return self.supports_json_schema

    @property
    def vision(self) -> bool:
        return self.supports_vision
```

And in `ChatModelProvider`:
```python
@runtime_checkable
class ChatModelProvider(Protocol):
    """Protocol for instantiating LangChain chat models with defined capabilities."""

    @property
    def name(self) -> str: ...

    def get_capabilities(self, model_name: str) -> ModelCapabilities: ...

    def get_pricing(self, model_name: str) -> ModelPricing: ...

    def build_chat_model(
        self,
        model_name: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        streaming: bool = True,
        **extra_kwargs: Any,
    ) -> BaseChatModel: ...

    # Alias for PROJECT.md § 126 parity
    def get_chat_model(
        self,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        streaming: bool = False,
        **extra_kwargs: Any,
    ) -> BaseChatModel: ...
```

### 6.2 Adapter Decoupling from Hardcoded Values

Currently, `OpenAIAdapter`, `AnthropicAdapter`, and `OpenRouterAdapter` hardcode pricing and capabilities in their `get_capabilities()` methods. 
To resolve this:
- Adapters can accept an optional `ModelCatalog` instance:
  `def __init__(self, settings: Settings | None = None, catalog: ModelCatalog | None = None) -> None:`
- If `catalog` is provided, `adapter.get_capabilities(model_name)` queries `catalog.get_capabilities(model_name)`.
- If no catalog is injected (e.g. standalone test mode), the adapter provides safe fallback defaults.
- In `build_chat_model`, adapters use API keys from settings or fall back safely to test stubs if unconfigured.

---

## 7. Concrete Unit Test Specifications

A comprehensive suite of unit tests should be placed in `tests/unit/test_model_catalog.py`:

### Test 1: `test_models_yaml_syntax_and_schema_validation`
- **Objective**: Verify that `config/models.yaml` is valid YAML and passes full Pydantic validation via `ModelsFileConfig`.
- **Assertions**:
  - `config.version == "1.0"`
  - `config.providers` contains `openai`, `anthropic`, `openrouter`, `openai_compatible`.
  - `config.models` contains `gpt-4o`, `gpt-4o-mini`, `claude-3-5-sonnet`, `claude-3-5-haiku`, etc.
  - Every model has `pricing.input_cost_per_mtok >= 0` and `context_window > 0`.
  - Every required role exists in `config.roles`: `generator`, `rewriter`, `agent`, `judge`, `decider`.

### Test 2: `test_model_catalog_alias_and_model_resolution`
- **Objective**: Verify that `resolve_model_id()` recursively resolves aliases.
- **Assertions**:
  - `catalog.resolve_model_id("gen-default") == "gpt-4o"`
  - `catalog.resolve_model_id("fast-default") == "gpt-4o-mini"`
  - `catalog.resolve_model_id("claude-sonnet") == "claude-3-5-sonnet"`
  - Non-existent alias raises `KeyError` with clear message listing available models.

### Test 3: `test_model_capabilities_and_pricing_conversion`
- **Objective**: Verify conversion from YAML schema to domain `ModelCapabilities` and `ModelPricing`.
- **Assertions**:
  - `caps = catalog.get_capabilities("gpt-4o")`
  - `caps.supports_tools is True`
  - `caps.supports_vision is True`
  - `caps.supports_logprobs is True`
  - `caps.context_window == 128_000`
  - `pricing = catalog.get_pricing("gpt-4o")`
  - `pricing.input_cost_per_mtok == 2.50`
  - `pricing.output_cost_per_mtok == 10.00`

### Test 4: `test_role_chain_resolution_with_settings_override`
- **Objective**: Verify that `resolve_role_chain` extracts primary + fallbacks and respects `Settings` overrides.
- **Assertions**:
  - Default: `catalog.resolve_role_chain("generator") == ["gpt-4o", "claude-3-5-sonnet", "openrouter-llama-3.1-70b"]`
  - When `settings.LLM_ROLE_GENERATOR_PRIMARY = "claude-3-5-sonnet"` and `settings.LLM_ROLE_GENERATOR_FALLBACKS = "gpt-4o-mini"`:
    `catalog.resolve_role_chain("generator", settings=custom_settings) == ["claude-3-5-sonnet", "gpt-4o-mini"]`.

### Test 5: `test_provider_registry_and_service_instantiation`
- **Objective**: Verify that `create_default_llm_registry()` creates a functional registry that creates adapters.
- **Assertions**:
  - `registry.available_providers()` contains `["anthropic", "openai", "openai_compatible", "openrouter"]`.
  - `registry.create("openai")` returns an `OpenAIAdapter`.
  - `registry.create("anthropic")` returns an `AnthropicAdapter`.

### Test 6: `test_llm_service_get_chat_model`
- **Objective**: Verify `LLMService.get_chat_model()` instantiates the right underlying LangChain chat model.
- **Assertions**:
  - For `"gpt-4o"`, returns a `ChatOpenAI` instance with model name `"gpt-4o"`.
  - For `"claude-3-5-sonnet"`, returns a `ChatAnthropic` instance.
  - Parameter overrides (`temperature=0.7`, `max_tokens=100`) take precedence over defaults.

### Test 7: `test_llm_service_role_fallback_chain`
- **Objective**: Verify `LLMService.get_role_fallback_chain("generator")` returns a configured `FallbackChain`.
- **Assertions**:
  - `chain = service.get_role_fallback_chain("generator")`
  - `chain.name == "role_chain_generator"`
  - `len(chain.members) >= 2`
  - Members are ordered according to the resolved role chain.

---

## 8. Implementation Roadmap & Task Breakdown

| Step | Action | Files Touched / Created | Risk / Note |
|---|---|---|---|
| 1 | Create configuration file | `config/models.yaml` | Strictly validate YAML against schema requirements |
| 2 | Add `MODELS_CONFIG_PATH` setting | `src/ragassist/shared/config/settings.py` & `.env.example` | Repository hygiene rule: synchronize `.env.example` immediately |
| 3 | Enhance capability & pricing contracts | `src/ragassist/platform/llm/ports.py` | Add `supports_vision`, property aliases, and parity methods |
| 4 | Implement catalog schemas and loader | `src/ragassist/platform/llm/catalog_models.py`, `catalog.py` | Use Pydantic v2 `ConfigDict(frozen=True)` |
| 5 | Implement default LLM registry & LLMService | `src/ragassist/platform/llm/service.py` | Wire `ProviderRegistry` and `FallbackChain` |
| 6 | Refactor adapters to leverage catalog | `src/ragassist/platform/llm/adapters/*.py` | Maintain backward compatibility for standalone instantiation |
| 7 | Create unit tests | `tests/unit/test_model_catalog.py` | Ensure 100% test pass rate |
