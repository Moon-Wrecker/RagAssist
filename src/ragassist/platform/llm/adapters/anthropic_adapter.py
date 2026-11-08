"""Anthropic Claude Chat Model Adapter."""

from typing import Any
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from ragassist.platform.llm.ports import ChatModelProvider, ModelCapabilities, ModelPricing
from ragassist.shared.config.settings import Settings, get_settings


class AnthropicAdapter(ChatModelProvider):
    """Adapter for Anthropic Claude models via langchain-anthropic."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "anthropic"

    def get_pricing(self, model_name: str) -> ModelPricing:
        low = model_name.lower()
        if "claude-3-haiku" in low:
            return ModelPricing(input_cost_per_mtok=0.25, output_cost_per_mtok=1.25)
        if "haiku" in low:
            return ModelPricing(input_cost_per_mtok=0.80, output_cost_per_mtok=4.00)
        return ModelPricing(input_cost_per_mtok=3.00, output_cost_per_mtok=15.00)

    def get_capabilities(self, model_name: str) -> ModelCapabilities:
        pricing = self.get_pricing(model_name)
        return ModelCapabilities(
            supports_tools=True,
            supports_json_schema=True,
            supports_streaming=True,
            supports_logprobs=False,
            supports_vision="sonnet" in model_name.lower(),
            context_window=200_000,
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
            api_key=self.settings.ANTHROPIC_API_KEY or "<redacted>",
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
