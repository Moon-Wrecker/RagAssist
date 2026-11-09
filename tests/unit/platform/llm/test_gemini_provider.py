"""Gemini as a first-class chat provider (ADR 0010): adapter, catalog entries and the skip-when-unconfigured rule.

Uses throwaway keys and a loopback fake server; nothing here touches the real Gemini endpoint.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml
from langchain_openai import ChatOpenAI
from support.contracts import ChatModelProviderContract
from support.settings import make_settings

from ragassist.platform.llm.adapters.gemini_adapter import GeminiAdapter
from ragassist.platform.llm.catalog import ModelCatalog
from ragassist.platform.llm.catalog_models import ModelsFileConfig
from ragassist.platform.llm.ports import ChatModelProvider
from ragassist.platform.llm.service import LLMService, create_default_llm_registry
from ragassist.shared.config.settings import UNCONFIGURED_KEY, Settings

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"
ROLES = ("generator", "rewriter", "agent", "judge", "decider")
LATEST_MODELS = {"gemini-flash-latest", "gemini-flash-lite-latest", "gemini-pro-latest"}


def secret_of(model: ChatOpenAI) -> str:
    return model.openai_api_key.get_secret_value()  # type: ignore[union-attr]


@pytest.fixture
def catalog() -> ModelCatalog:
    return ModelCatalog.load_from_yaml("config/models.yaml")


def gemini_models(catalog: ModelCatalog, chain: list[str]) -> list[str]:
    return [m for m in chain if catalog.get_model(m).provider == "gemini"]


class TestGeminiAdapter(ChatModelProviderContract):
    model_name = "gemini-flash-latest"

    @pytest.fixture
    def provider(self) -> ChatModelProvider:
        return GeminiAdapter(make_settings(GEMINI_API_KEY=""))

    def test_pricing_comes_from_the_catalog(self, provider: ChatModelProvider) -> None:
        pricing = provider.get_pricing("gemini-3.5-flash-lite")
        assert (pricing.input_cost_per_mtok, pricing.output_cost_per_mtok) == (0.30, 2.50)

    def test_capabilities(self, provider: ChatModelProvider) -> None:
        caps = provider.get_capabilities(self.model_name)
        assert caps.supports_tools and caps.supports_json_schema and caps.supports_vision
        assert caps.context_window == 1_048_576

    def test_targets_the_configured_gemini_endpoint(self) -> None:
        adapter = GeminiAdapter(make_settings(GEMINI_BASE_URL="http://gemini.internal:9/v1/"))
        model = adapter.build_chat_model("gemini-flash-latest")
        assert model.openai_api_base == "http://gemini.internal:9/v1/"  # type: ignore[attr-defined]

    def test_uses_the_gemini_key(self) -> None:
        key = secrets.token_urlsafe(24)
        model = GeminiAdapter(make_settings(GEMINI_API_KEY=key)).build_chat_model(
            "gemini-flash-latest"
        )
        assert secret_of(model) == key  # type: ignore[arg-type]

    def test_without_a_key_it_still_builds_with_the_placeholder(self) -> None:
        model = GeminiAdapter(make_settings(GEMINI_API_KEY="")).build_chat_model(
            "gemini-flash-latest"
        )
        assert secret_of(model) == UNCONFIGURED_KEY  # type: ignore[arg-type]

    def test_never_sends_another_providers_key(self) -> None:
        """Key isolation: the OpenAI and the local-server keys must not reach Google."""
        openai_key, local_key = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        adapter = GeminiAdapter(
            make_settings(
                GEMINI_API_KEY="", OPENAI_API_KEY=openai_key, OPENAI_COMPATIBLE_API_KEY=local_key
            )
        )
        sent = secret_of(adapter.build_chat_model("gemini-flash-latest"))  # type: ignore[arg-type]
        assert sent not in {openai_key, local_key}

    def test_the_local_openai_compatible_setup_is_untouched(self) -> None:
        """Configuring Gemini must not redirect an Ollama-style OPENAI_COMPATIBLE_* endpoint to Google."""
        from ragassist.platform.llm.adapters.openrouter_adapter import OpenAICompatibleAdapter

        settings = make_settings(
            GEMINI_API_KEY=secrets.token_urlsafe(24),
            OPENAI_COMPATIBLE_BASE_URL="http://localhost:11434/v1",
        )
        local = OpenAICompatibleAdapter(settings).build_chat_model("llama3.1:8b")
        assert local.openai_api_base == "http://localhost:11434/v1"  # type: ignore[attr-defined]


class _ChatServer:
    """Loopback OpenAI-style chat endpoint that records what the SDK sent."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(
                    {"path": self.path, "auth": self.headers.get("Authorization"), "body": body}
                )
                payload = json.dumps(
                    {
                        "id": "x",
                        "object": "chat.completion",
                        "created": 0,
                        "model": body["model"],
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "pong"},
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> _ChatServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1beta/openai/"


@pytest.fixture
def chat_server() -> Iterator[_ChatServer]:
    server = _ChatServer().start()
    try:
        yield server
    finally:
        server.stop()


class TestGeminiOverTheWire:
    async def test_posts_to_chat_completions_with_a_bearer_key(
        self, chat_server: _ChatServer
    ) -> None:
        key = secrets.token_urlsafe(24)
        settings = make_settings(GEMINI_API_KEY=key, GEMINI_BASE_URL=chat_server.base_url)
        model = GeminiAdapter(settings).build_chat_model("gemini-flash-latest", streaming=False)
        reply = await model.ainvoke("ping")
        assert reply.content == "pong"
        sent = chat_server.requests[-1]
        assert sent["path"] == "/v1beta/openai/chat/completions"
        assert sent["auth"] == f"Bearer {key}"
        assert sent["body"]["model"] == "gemini-flash-latest"


class TestCatalogEntries:
    def test_the_provider_is_declared_and_optional(self) -> None:
        config = ModelsFileConfig.model_validate(
            yaml.safe_load(Path("config/models.yaml").read_text(encoding="utf-8"))
        )
        gemini = config.providers["gemini"]
        assert (gemini.adapter, gemini.api_key_env, gemini.base_url_env) == (
            "gemini",
            "GEMINI_API_KEY",
            "GEMINI_BASE_URL",
        )
        assert gemini.skip_when_unconfigured is True
        assert not any(
            p.skip_when_unconfigured for name, p in config.providers.items() if name != "gemini"
        )

    def test_the_latest_models_and_pinned_models_are_listed(self, catalog: ModelCatalog) -> None:
        for key in LATEST_MODELS | {"gemini-3.8-flash", "gemini-3.5-flash-lite"}:
            model = catalog.get_model(key)
            assert model.provider == "gemini"
            assert (model.context_window, model.max_output_tokens) == (1_048_576, 65_536)
            caps = catalog.get_capabilities(key)
            assert caps.supports_tools and caps.supports_json_schema and caps.supports_streaming
        assert catalog.get_model("gemini-flash-latest").model_name == "gemini-flash-latest"

    @pytest.mark.parametrize(
        ("alias", "target"),
        [
            ("gemini-flash", "gemini-flash-latest"),
            ("gemini-flash-lite", "gemini-flash-lite-latest"),
            ("gemini-pro", "gemini-pro-latest"),
            ("gen-gemini", "gemini-flash-latest"),
        ],
    )
    def test_aliases(self, catalog: ModelCatalog, alias: str, target: str) -> None:
        assert catalog.resolve_model_id(alias) == target

    def test_flash_pricing(self, catalog: ModelCatalog) -> None:
        pricing = catalog.get_pricing("gemini-flash-latest")
        assert (pricing.input_cost_per_mtok, pricing.output_cost_per_mtok) == (0.75, 3.75)

    def test_the_registry_knows_gemini(self) -> None:
        assert "gemini" in create_default_llm_registry().available_providers()

    def test_gemini_is_never_a_default_primary(self, catalog: ModelCatalog) -> None:
        for role in ROLES:
            assert catalog.get_model(catalog.get_role_mapping(role).primary).provider != "gemini"


class TestUnconfiguredGeminiIsSkipped:
    @pytest.mark.parametrize("role", ROLES)
    def test_with_no_key_the_chain_has_no_gemini_member(
        self, catalog: ModelCatalog, role: str
    ) -> None:
        settings = make_settings(GEMINI_API_KEY="")
        assert gemini_models(catalog, catalog.resolve_role_chain(role, settings=settings)) == []

    @pytest.mark.parametrize("role", ROLES)
    def test_with_no_key_the_chain_equals_the_pre_gemini_chain(
        self, catalog: ModelCatalog, role: str
    ) -> None:
        chain = catalog.resolve_role_chain(role, settings=make_settings(GEMINI_API_KEY=""))
        mapping = catalog.get_role_mapping(role)
        original = [
            m
            for m in [mapping.primary, *mapping.fallbacks]
            if catalog.get_model(m).provider != "gemini"
        ]
        assert chain == [catalog.resolve_model_id(m) for m in original]

    @pytest.mark.parametrize("role", ROLES)
    def test_with_a_key_gemini_is_the_last_fallback(self, catalog: ModelCatalog, role: str) -> None:
        settings = make_settings(GEMINI_API_KEY=secrets.token_urlsafe(24))
        chain = catalog.resolve_role_chain(role, settings=settings)
        assert len(chain) > 1
        assert catalog.get_model(chain[-1]).provider == "gemini"

    def test_whitespace_only_key_counts_as_unset(self, catalog: ModelCatalog) -> None:
        settings = make_settings(GEMINI_API_KEY="   ")
        chain = catalog.resolve_role_chain("generator", settings=settings)
        assert gemini_models(catalog, chain) == []

    def test_an_explicit_gemini_primary_is_kept_even_without_a_key(
        self, catalog: ModelCatalog
    ) -> None:
        settings = make_settings(GEMINI_API_KEY="", LLM_ROLE_GENERATOR_PRIMARY="gemini-flash")
        assert (
            catalog.resolve_role_chain("generator", settings=settings)[0] == "gemini-flash-latest"
        )

    def test_a_gemini_fallback_override_is_skipped_without_a_key(
        self, catalog: ModelCatalog
    ) -> None:
        settings = make_settings(
            GEMINI_API_KEY="", LLM_ROLE_GENERATOR_FALLBACKS="gemini-pro,claude-3-5-sonnet"
        )
        chain = catalog.resolve_role_chain("generator", settings=settings)
        assert chain == ["gpt-4o", "claude-3-5-sonnet"]

    def test_the_other_providers_are_never_skipped(self, catalog: ModelCatalog) -> None:
        settings = make_settings(
            OPENAI_API_KEY="", ANTHROPIC_API_KEY="", OPENROUTER_API_KEY="", GEMINI_API_KEY=""
        )
        assert catalog.resolve_role_chain("generator", settings=settings) == [
            "gpt-4o",
            "claude-3-5-sonnet",
            "openrouter-llama-3.1-70b",
        ]

    def test_without_settings_nothing_is_filtered(self, catalog: ModelCatalog) -> None:
        assert "gemini-flash-latest" in catalog.resolve_role_chain("generator")

    @pytest.mark.parametrize("configured", [False, True])
    def test_the_service_builds_only_the_configured_members(
        self, catalog: ModelCatalog, configured: bool
    ) -> None:
        settings = make_settings(GEMINI_API_KEY=secrets.token_urlsafe(24) if configured else "")
        service = LLMService(catalog, create_default_llm_registry(settings), settings)
        chain = service.get_role_fallback_chain("generator")
        names = [getattr(m, "name", "") for m in chain.members]
        assert len(names) == (4 if configured else 3)
        assert ("gemini-flash-latest" in names) is configured


class TestGeminiSettings:
    def test_the_key_is_optional_and_empty_by_default(self) -> None:
        assert Settings.model_fields["GEMINI_API_KEY"].default == ""

    def test_the_endpoint_has_no_code_default(self) -> None:
        assert Settings.model_fields["GEMINI_BASE_URL"].is_required()

    def test_the_template_points_at_the_gemini_endpoint(self) -> None:
        from dotenv import dotenv_values

        values = dotenv_values(Path(".env.example"))
        assert values["GEMINI_BASE_URL"] == GEMINI_ENDPOINT
        assert values["GEMINI_API_KEY"] == ""

    def test_the_key_is_masked_in_repr_and_json(self) -> None:
        key = secrets.token_urlsafe(24)
        settings = make_settings(GEMINI_API_KEY=key)
        assert key not in repr(settings)
        assert key not in settings.model_dump_json()
