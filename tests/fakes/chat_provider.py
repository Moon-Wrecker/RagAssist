"""A fake ``ChatModelProvider`` whose models replay scripts.

Lets service-level tests prove "swap the model by configuration" and failover behaviour without any
SDK or network: each model *name* gets its own :class:`ScriptedChatModel`.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from fakes.chat_model import ScriptedChatModel
from ragassist.platform.llm.ports import ModelCapabilities, ModelPricing


class ScriptedProvider:
    def __init__(self, name: str = "scripted", scripts: dict[str, list[Any]] | None = None) -> None:
        self._name = name
        self.scripts = scripts or {}
        self.built: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    def get_capabilities(self, model_name: str) -> ModelCapabilities:
        return ModelCapabilities()

    def get_pricing(self, model_name: str) -> ModelPricing:
        return ModelPricing()

    def build_chat_model(
        self,
        model_name: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        streaming: bool = True,
        **extra_kwargs: Any,
    ) -> BaseChatModel:
        self.built.append(
            {
                "model_name": model_name,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "streaming": streaming,
                **extra_kwargs,
            }
        )
        return ScriptedChatModel(
            script=list(self.scripts.get(model_name, ["ok"])), label=model_name
        )

    def get_chat_model(self, model: str, **kwargs: Any) -> BaseChatModel:
        return self.build_chat_model(model, **kwargs)
