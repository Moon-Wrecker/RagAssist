"""High-level LLM Service orchestrating model instantiation and fallback chains."""

from typing import Any

import structlog
from langchain_core.language_models.chat_models import BaseChatModel

from ragassist.platform.llm.adapters.anthropic_adapter import AnthropicAdapter
from ragassist.platform.llm.adapters.gemini_adapter import GeminiAdapter
from ragassist.platform.llm.adapters.openai_adapter import OpenAIAdapter
from ragassist.platform.llm.adapters.openrouter_adapter import (
    OpenAICompatibleAdapter,
    OpenRouterAdapter,
)
from ragassist.platform.llm.catalog import ModelCatalog
from ragassist.platform.llm.ports import ChatModelProvider, ModelCapabilities, ModelPricing
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.registry import ProviderRegistry
from ragassist.shared.resilience import FallbackChain

logger = structlog.get_logger(__name__)


def create_default_llm_registry(settings: Settings | None = None) -> ProviderRegistry[ChatModelProvider]:
    """Create and populate the default LLM ChatModelProvider registry."""
    active_settings = settings or get_settings()
    registry = ProviderRegistry[ChatModelProvider]("llm_chat_provider")

    registry.register("openai", lambda: OpenAIAdapter(settings=active_settings))
    registry.register("anthropic", lambda: AnthropicAdapter(settings=active_settings))
    registry.register("openrouter", lambda: OpenRouterAdapter(settings=active_settings))
    registry.register("gemini", lambda: GeminiAdapter(settings=active_settings))
    registry.register("openai_compatible", lambda: OpenAICompatibleAdapter(settings=active_settings))

    return registry


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
            try:
                setattr(model_instance, "name", mid)
            except (AttributeError, TypeError, ValueError) as exc:
                logger.debug("llm.model_name_not_set", model=mid, error=str(exc))
            models.append(model_instance)

        return FallbackChain[BaseChatModel](name=f"role_chain_{role}", members=models)
