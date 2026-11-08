"""Abstract ports and capability contracts for Chat and Embedding providers."""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from langchain_core.language_models.chat_models import BaseChatModel

from ragassist.platform.embeddings.ports import EmbeddingProvider  # re-export for backward compatibility


@dataclass(frozen=True)
class ModelPricing:
    """Token pricing per million tokens in USD."""

    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0


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


@runtime_checkable
class ChatModelProvider(Protocol):
    """Protocol for instantiating LangChain chat models with defined capabilities."""

    @property
    def name(self) -> str:
        """Provider adapter identifier."""
        ...

    def get_capabilities(self, model_name: str) -> ModelCapabilities:
        """Return declared capabilities for a specific model name."""
        ...

    def get_pricing(self, model_name: str) -> ModelPricing:
        """Return declared token pricing for a specific model name."""
        ...

    def build_chat_model(
        self,
        model_name: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        streaming: bool = True,
        **extra_kwargs: Any,
    ) -> BaseChatModel:
        """Instantiate a configured BaseChatModel instance."""
        ...

    def get_chat_model(
        self,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        streaming: bool = False,
        **extra_kwargs: Any,
    ) -> BaseChatModel:
        """Alias for build_chat_model for PROJECT.md § 126 parity."""
        ...


__all__ = [
    "ChatModelProvider",
    "EmbeddingProvider",
    "ModelCapabilities",
    "ModelPricing",
]
