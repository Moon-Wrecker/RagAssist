"""OpenRouter and OpenAI-Compatible Chat Model Adapters."""

from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from ragassist.platform.llm.ports import ChatModelProvider, ModelCapabilities, ModelPricing
from ragassist.shared.config.settings import Settings, get_settings


class OpenRouterAdapter(ChatModelProvider):
    """Adapter for OpenRouter models using OpenAI-compatible routing protocol."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "openrouter"

    def get_pricing(self, model_name: str) -> ModelPricing:
        low = model_name.lower()
        if "llama" in low:
            return ModelPricing(input_cost_per_mtok=0.40, output_cost_per_mtok=0.40)
        if "mistral" in low:
            return ModelPricing(input_cost_per_mtok=2.00, output_cost_per_mtok=6.00)
        return ModelPricing(input_cost_per_mtok=0.80, output_cost_per_mtok=2.40)

    def get_capabilities(self, model_name: str) -> ModelCapabilities:
        low = model_name.lower()
        if "llama-3.1" in low or "llama-3" in low or "llama3" in low:
            context_window = 131_072
        else:
            context_window = 128_000

        return ModelCapabilities(
            supports_tools=True,
            supports_json_schema="claude" in low or "gpt" in low,
            supports_streaming=True,
            supports_logprobs=False,
            supports_vision=False,
            context_window=context_window,
            pricing=self.get_pricing(model_name),
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
            api_key=self.settings.OPENROUTER_API_KEY or "dummy-key-for-testing",
            base_url="https://openrouter.ai/api/v1",
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=streaming,
            default_headers={
                "HTTP-Referer": "https://github.com/ragassist/ragassist",
                "X-Title": "RagAssist",
            },
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


class OpenAICompatibleAdapter(ChatModelProvider):
    """Adapter for custom self-hosted or proxy OpenAI-compatible endpoints (Ollama, vLLM, Groq, LM Studio)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "openai_compatible"

    def get_pricing(self, model_name: str) -> ModelPricing:
        return ModelPricing(input_cost_per_mtok=0.0, output_cost_per_mtok=0.0)

    def get_capabilities(self, model_name: str) -> ModelCapabilities:
        low = model_name.lower()
        if "llama3.1" in low or "32768" in low:
            context_window = 32_768
        else:
            context_window = 32_000

        return ModelCapabilities(
            supports_tools=True,
            supports_json_schema=True,
            supports_streaming=True,
            supports_logprobs=False,
            supports_vision=False,
            context_window=context_window,
            pricing=self.get_pricing(model_name),
        )

    def build_chat_model(
        self,
        model_name: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        streaming: bool = True,
        base_url: str | None = None,
        api_key: str | None = None,
        **extra_kwargs: Any,
    ) -> BaseChatModel:
        url = base_url or self.settings.OPENAI_COMPATIBLE_BASE_URL
        key = api_key or self.settings.OPENAI_COMPATIBLE_API_KEY or "ollama"
        return ChatOpenAI(
            model=model_name,
            api_key=key,
            base_url=url,
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
