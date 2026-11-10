"""Anthropic Claude Chat Model Adapter."""

from typing import Any
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from ragassist.platform.llm.ports import ChatModelProvider, ModelCapabilities, ModelPricing
from ragassist.shared.config.settings import Settings, UNCONFIGURED_KEY, get_settings


class AnthropicAdapter(ChatModelProvider):
    """Adapter for Anthropic Claude models via langchain-anthropic."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "anthropic"

    def get_pricing(self, model_name: str) -> ModelPricing:
        from ragassist.platform.llm.catalog import ModelCatalog

        catalog = ModelCatalog.load_from_yaml(self.settings.MODELS_CONFIG_PATH)
        return catalog.resolve_pricing(model_name, provider_name="anthropic")

    def get_capabilities(self, model_name: str) -> ModelCapabilities:
        from ragassist.platform.llm.catalog import ModelCatalog

        pricing = self.get_pricing(model_name)
        # The catalogue is the source of truth for models it lists (Claude 5.x: 1M window, vision on
        # every tier); the heuristics only cover model names the catalogue does not know.
        catalog = ModelCatalog.load_from_yaml(self.settings.MODELS_CONFIG_PATH)
        known = catalog.find_model(model_name, provider_name="anthropic")
        return ModelCapabilities(
            supports_tools=True,
            supports_json_schema=True,
            supports_streaming=True,
            supports_logprobs=False,
            supports_vision=known.capabilities.vision if known else "sonnet" in model_name.lower(),
            context_window=known.context_window if known else 200_000,
            pricing=pricing,
        )

    def build_chat_model(
        self,
        model_name: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        streaming: bool = True,
        **extra_kwargs: Any,
    ) -> BaseChatModel:
        return ChatAnthropic(
            model_name=model_name,
            api_key=self.settings.ANTHROPIC_API_KEY or UNCONFIGURED_KEY,
            temperature=temperature,
            max_tokens_to_sample=max_tokens or 4096,
            streaming=streaming,
            **extra_kwargs,
        )

    def get_chat_model(
        self,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        streaming: bool = False,
        **extra_kwargs: Any,
    ) -> BaseChatModel:
        return self.build_chat_model(
            model_name=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=streaming,
            **extra_kwargs,
        )
