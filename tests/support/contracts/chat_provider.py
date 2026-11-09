"""Contract for ``ChatModelProvider`` adapters (OpenAI, Anthropic, OpenRouter, compatible)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from ragassist.platform.llm.ports import ChatModelProvider, ModelCapabilities, ModelPricing


class ChatModelProviderContract:
    """Subclass and provide the ``provider`` fixture and ``model_name``."""

    model_name: str = "some-model"

    @pytest.fixture
    def provider(self) -> ChatModelProvider:  # pragma: no cover - overridden
        raise NotImplementedError

    # -- identity -------------------------------------------------------------------------------
    def test_conforms_to_the_port(self, provider: ChatModelProvider) -> None:
        assert isinstance(provider, ChatModelProvider)

    def test_has_a_stable_non_empty_name(self, provider: ChatModelProvider) -> None:
        assert isinstance(provider.name, str) and provider.name
        assert provider.name == provider.name.lower().strip()

    # -- capabilities & pricing -----------------------------------------------------------------
    def test_capabilities_are_well_formed(self, provider: ChatModelProvider) -> None:
        caps = provider.get_capabilities(self.model_name)
        assert isinstance(caps, ModelCapabilities)
        assert caps.context_window > 0
        assert isinstance(caps.pricing, ModelPricing)

    def test_capabilities_are_immutable(self, provider: ChatModelProvider) -> None:
        caps = provider.get_capabilities(self.model_name)
        with pytest.raises(FrozenInstanceError):
            caps.supports_tools = not caps.supports_tools  # type: ignore[misc]

    def test_pricing_is_non_negative_and_consistent_with_capabilities(
        self, provider: ChatModelProvider
    ) -> None:
        pricing = provider.get_pricing(self.model_name)
        assert isinstance(pricing, ModelPricing)
        assert pricing.input_cost_per_mtok >= 0 and pricing.output_cost_per_mtok >= 0
        assert pricing == provider.get_capabilities(self.model_name).pricing

    def test_capabilities_are_deterministic(self, provider: ChatModelProvider) -> None:
        assert provider.get_capabilities(self.model_name) == provider.get_capabilities(
            self.model_name
        )

    # -- building models ------------------------------------------------------------------------
    def test_build_returns_a_chat_model(self, provider: ChatModelProvider) -> None:
        assert isinstance(provider.build_chat_model(self.model_name), BaseChatModel)

    def test_build_applies_temperature_and_streaming(self, provider: ChatModelProvider) -> None:
        model = provider.build_chat_model(self.model_name, temperature=0.25, streaming=False)
        assert model.temperature == pytest.approx(0.25)  # type: ignore[attr-defined]
        assert model.streaming is False  # type: ignore[attr-defined]
        model = provider.build_chat_model(self.model_name, streaming=True)
        assert model.streaming is True  # type: ignore[attr-defined]

    def test_build_needs_no_network_and_no_api_key(self, provider: ChatModelProvider) -> None:
        """Building must be cheap and offline so the app can start (and tests can run) keyless."""
        provider.build_chat_model(self.model_name)

    def test_each_build_is_an_independent_instance(self, provider: ChatModelProvider) -> None:
        assert provider.build_chat_model(self.model_name) is not provider.build_chat_model(
            self.model_name
        )

    def test_get_chat_model_alias_matches_build(self, provider: ChatModelProvider) -> None:
        model = provider.get_chat_model(self.model_name, temperature=0.4, streaming=False)
        assert isinstance(model, BaseChatModel)
        assert model.temperature == pytest.approx(0.4)  # type: ignore[attr-defined]
        assert model.streaming is False  # type: ignore[attr-defined]
