"""OpenAI Chat Model Adapter."""

from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from ragassist.platform.llm.ports import ChatModelProvider, ModelCapabilities, ModelPricing
from ragassist.shared.config.settings import Settings, get_settings


class OpenAIAdapter(ChatModelProvider):
    """Adapter for native OpenAI models via langchain-openai."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "openai"

    def get_pricing(self, model_name: str) -> ModelPricing:
        if "mini" in model_name.lower():
            return ModelPricing(input_cost_per_mtok=0.15, output_cost_per_mtok=0.60)
        return ModelPricing(input_cost_per_mtok=2.50, output_cost_per_mtok=10.00)

    def get_capabilities(self, model_name: str) -> ModelCapabilities:
        pricing = self.get_pricing(model_name)
        return ModelCapabilities(
            supports_tools=True,
            supports_json_schema=True,
            supports_streaming=True,
            supports_logprobs=True,
            supports_vision=True,
            context_window=128_000,
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
        return ChatOpenAI(
            model=model_name,
            api_key=self.settings.OPENAI_API_KEY or "dummy-key-for-testing",
            temperature=temperature,
            max_tokens=max_tokens,
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
