"""Chat model provider adapters (features 8 and 9).

Every adapter runs the shared ``ChatModelProviderContract``; the classes below add only what is
specific to that adapter (pricing tables, base URLs, key handling).
"""

from __future__ import annotations

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from support.contracts import ChatModelProviderContract
from support.settings import make_settings

from ragassist.platform.llm.adapters.anthropic_adapter import AnthropicAdapter
from ragassist.platform.llm.adapters.openai_adapter import OpenAIAdapter
from ragassist.platform.llm.adapters.openrouter_adapter import (
    OpenAICompatibleAdapter,
    OpenRouterAdapter,
)
from ragassist.platform.llm.ports import ChatModelProvider

KEYLESS = {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENROUTER_API_KEY": ""}


def secret(model: ChatOpenAI) -> str:
    return model.openai_api_key.get_secret_value()  # type: ignore[union-attr]


class TestOpenAIAdapter(ChatModelProviderContract):
    model_name = "gpt-4o"

    @pytest.fixture
    def provider(self) -> ChatModelProvider:
        return OpenAIAdapter(make_settings(**KEYLESS))

    @pytest.mark.parametrize(
        ("model", "inp", "out"),
        [("gpt-4o", 2.50, 10.00), ("gpt-4o-mini", 0.15, 0.60), ("GPT-4O-MINI", 0.15, 0.60)],
    )
    def test_pricing_table(
        self, provider: ChatModelProvider, model: str, inp: float, out: float
    ) -> None:
        pricing = provider.get_pricing(model)
        assert (pricing.input_cost_per_mtok, pricing.output_cost_per_mtok) == (inp, out)

    def test_capabilities(self, provider: ChatModelProvider) -> None:
        caps = provider.get_capabilities("gpt-4o")
        assert caps.supports_tools and caps.supports_json_schema and caps.supports_logprobs
        assert caps.context_window == 128_000

    def test_builds_a_chatopenai_with_the_requested_parameters(
        self, provider: ChatModelProvider
    ) -> None:
        model = provider.build_chat_model("gpt-4o-mini", temperature=0.3, max_tokens=77)
        assert isinstance(model, ChatOpenAI)
        assert (model.model_name, model.temperature, model.max_tokens) == ("gpt-4o-mini", 0.3, 77)

    def test_uses_the_configured_api_key(self) -> None:
        adapter = OpenAIAdapter(make_settings(OPENAI_API_KEY="sk-real-key"))
        assert secret(adapter.build_chat_model("gpt-4o")) == "sk-real-key"  # type: ignore[arg-type]

    def test_extra_kwargs_reach_the_model(self, provider: ChatModelProvider) -> None:
        model = provider.build_chat_model("gpt-4o", seed=1234)
        assert model.seed == 1234  # type: ignore[attr-defined]


class TestAnthropicAdapter(ChatModelProviderContract):
    model_name = "claude-3-5-sonnet-20241022"

    @pytest.fixture
    def provider(self) -> ChatModelProvider:
        return AnthropicAdapter(make_settings(**KEYLESS))

    @pytest.mark.parametrize(
        ("model", "inp", "out"),
        [
            ("claude-3-5-sonnet-20241022", 3.00, 15.00),
            ("claude-3-5-haiku-20241022", 0.80, 4.00),
            ("claude-haiku-5-5", 0.10, 0.50),
            ("claude-sonnet-5-5", 2.00, 10.00),
            ("CLAUDE-HAIKU", 0.10, 0.50),
        ],
    )
    def test_pricing_table(
        self, provider: ChatModelProvider, model: str, inp: float, out: float
    ) -> None:
        pricing = provider.get_pricing(model)
        assert (pricing.input_cost_per_mtok, pricing.output_cost_per_mtok) == (inp, out)

    def test_capabilities(self, provider: ChatModelProvider) -> None:
        caps = provider.get_capabilities("claude-3-5-sonnet-20241022")
        assert caps.context_window == 200_000
        assert caps.supports_tools and not caps.supports_logprobs

    @pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-sonnet-5-5"])
    def test_claude_5_capabilities_come_from_the_catalogue(
        self, provider: ChatModelProvider, model: str
    ) -> None:
        caps = provider.get_capabilities(model)
        assert caps.context_window == 1_000_000
        assert caps.supports_vision

    def test_builds_a_chatanthropic(self, provider: ChatModelProvider) -> None:
        model = provider.build_chat_model(
            "claude-3-5-haiku-20241022", temperature=0.2, max_tokens=123
        )
        assert isinstance(model, ChatAnthropic)
        assert model.model == "claude-3-5-haiku-20241022"
        assert model.max_tokens == 123

    def test_output_limit_defaults_to_4096_when_unspecified(
        self, provider: ChatModelProvider
    ) -> None:
        """Anthropic requires an explicit max_tokens; the adapter supplies a safe default."""
        assert provider.build_chat_model(self.model_name).max_tokens == 4096  # type: ignore[attr-defined]


class TestOpenRouterAdapter(ChatModelProviderContract):
    model_name = "meta-llama/llama-3.1-70b-instruct"

    @pytest.fixture
    def provider(self) -> ChatModelProvider:
        return OpenRouterAdapter(make_settings(**KEYLESS))

    def test_routes_through_the_openrouter_endpoint_with_attribution_headers(
        self, provider: ChatModelProvider
    ) -> None:
        model = provider.build_chat_model(self.model_name)
        assert isinstance(model, ChatOpenAI)
        assert model.openai_api_base == "https://openrouter.ai/api/v1"
        assert model.default_headers["X-Title"] == "RagAssist"  # type: ignore[index]
        assert "HTTP-Referer" in model.default_headers  # type: ignore[operator]

    @pytest.mark.parametrize(
        ("model", "json_schema"),
        [
            ("openai/gpt-4o", True),
            ("anthropic/claude-3.5-sonnet", True),
            ("meta-llama/llama-3.1-70b-instruct", False),
            ("mistralai/mistral-large-2407", False),
        ],
    )
    def test_json_schema_support_is_inferred_from_the_model_family(
        self, provider: ChatModelProvider, model: str, json_schema: bool
    ) -> None:
        assert provider.get_capabilities(model).supports_json_schema is json_schema

    def test_uses_the_openrouter_key(self) -> None:
        adapter = OpenRouterAdapter(make_settings(OPENROUTER_API_KEY="or-key"))
        assert secret(adapter.build_chat_model("openai/gpt-4o")) == "or-key"  # type: ignore[arg-type]

    def test_does_not_send_the_openai_key_to_openrouter(self) -> None:
        """Key isolation: a provider must never receive another provider's credential."""
        adapter = OpenRouterAdapter(
            make_settings(OPENAI_API_KEY="sk-openai", OPENROUTER_API_KEY="")
        )
        assert secret(adapter.build_chat_model("openai/gpt-4o")) != "sk-openai"  # type: ignore[arg-type]


class TestOpenAICompatibleAdapter(ChatModelProviderContract):
    model_name = "llama3.1:8b"

    @pytest.fixture
    def provider(self) -> ChatModelProvider:
        return OpenAICompatibleAdapter(make_settings(**KEYLESS))

    def test_is_free_to_run(self, provider: ChatModelProvider) -> None:
        pricing = provider.get_pricing(self.model_name)
        assert (pricing.input_cost_per_mtok, pricing.output_cost_per_mtok) == (0.0, 0.0)

    def test_targets_the_configured_local_endpoint(self) -> None:
        adapter = OpenAICompatibleAdapter(
            make_settings(OPENAI_COMPATIBLE_BASE_URL="http://vllm.internal:8000/v1")
        )
        assert adapter.build_chat_model("m").openai_api_base == "http://vllm.internal:8000/v1"  # type: ignore[attr-defined]

    def test_explicit_base_url_and_key_override_settings(self, provider: ChatModelProvider) -> None:
        model = provider.build_chat_model("m", base_url="http://other:1/v1", api_key="k-explicit")  # type: ignore[call-arg]
        assert model.openai_api_base == "http://other:1/v1"  # type: ignore[attr-defined]
        assert secret(model) == "k-explicit"  # type: ignore[arg-type]

    def test_never_forwards_a_cloud_key_to_a_local_server(self) -> None:
        adapter = OpenAICompatibleAdapter(
            make_settings(OPENAI_API_KEY="sk-openai", OPENAI_COMPATIBLE_API_KEY="")
        )
        assert secret(adapter.build_chat_model("m")) != "sk-openai"  # type: ignore[arg-type]
