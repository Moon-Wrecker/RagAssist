"""Google Gemini chat adapter, served through Google's OpenAI-compatible endpoint.

Goal: let Gemini models back any LLM role next to OpenAI, Anthropic, OpenRouter and a local server, without a new SDK.

Consulted (decision in brackets):
* https://ai.google.dev/gemini-api/docs/openai (redirects to aistudio.google.com/docs/openai): base URL
  ``https://generativelanguage.googleapis.com/v1beta/openai/``, ``Authorization: Bearer <key>``, function calling,
  structured output and streaming are supported [reuse ``ChatOpenAI`` from ``langchain-openai`` instead of adding
  ``langchain-google-genai``].
* https://ai.google.dev/gemini-api/docs/models and .../pricing: model codes, limits, prices [recorded in
  ``config/models.yaml`` and ADR 0010].
The endpoint and key come from ``GEMINI_BASE_URL`` / ``GEMINI_API_KEY``, never from code; Gemini keeps its own pair of
settings so a local ``OPENAI_COMPATIBLE_*`` (Ollama) setup is untouched, and no other provider's key is ever sent here.
"""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from ragassist.platform.llm.ports import ChatModelProvider, ModelCapabilities, ModelPricing
from ragassist.shared.config.settings import UNCONFIGURED_KEY, Settings, get_settings

_DEFAULT_CONTEXT_WINDOW = 1_048_576


class GeminiAdapter(ChatModelProvider):
    """Adapter for Gemini models on the OpenAI-compatible Generative Language endpoint."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def name(self) -> str:
        return "gemini"

    def get_pricing(self, model_name: str) -> ModelPricing:
        from ragassist.platform.llm.catalog import ModelCatalog

        catalog = ModelCatalog.load_from_yaml(self.settings.MODELS_CONFIG_PATH)
        return catalog.resolve_pricing(model_name, provider_name="gemini")

    def get_capabilities(self, model_name: str) -> ModelCapabilities:
        return ModelCapabilities(
            supports_tools=True,
            supports_json_schema=True,
            supports_streaming=True,
            supports_logprobs=False,
            supports_vision=True,
            context_window=_DEFAULT_CONTEXT_WINDOW,
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
            api_key=self.settings.GEMINI_API_KEY or UNCONFIGURED_KEY,
            base_url=self.settings.GEMINI_BASE_URL,
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
