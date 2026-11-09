"""LLMService: builds models from catalog entries and role fallback chains (feature 8, plan P1).

Acceptance from the plan: "the same prompt runs on OpenAI, OpenRouter and Ollama through config
only" and "we record which model actually answered".
"""

from __future__ import annotations

import pytest
from fakes.chat_provider import ScriptedProvider
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from support.settings import make_settings

from ragassist.platform.llm.catalog import ModelCatalog
from ragassist.platform.llm.catalog_models import ModelsFileConfig
from ragassist.platform.llm.ports import ChatModelProvider
from ragassist.platform.llm.service import LLMService, create_default_llm_registry
from ragassist.shared.registry import ProviderRegistry
from unit.platform.llm.test_catalog import NO_ROLE_OVERRIDES, YAML_PATH

KEYLESS = {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENROUTER_API_KEY": ""}


def catalog() -> ModelCatalog:
    return ModelCatalog(
        ModelsFileConfig.model_validate(
            {
                "providers": {"p1": {"adapter": "p1"}, "p2": {"adapter": "p2"}},
                "models": {
                    "big": {
                        "provider": "p1",
                        "model_name": "big-v1",
                        "max_output_tokens": 2000,
                        "default_params": {"temperature": 0.7},
                    },
                    "small": {"provider": "p2", "model_name": "small-v1", "max_output_tokens": 500},
                    "backup": {"provider": "p2", "model_name": "backup-v1"},
                },
                "aliases": {"default": "big"},
                "roles": {"generator": {"primary": "default", "fallbacks": ["small", "backup"]}},
            }
        )
    )


def service(p1: ScriptedProvider, p2: ScriptedProvider) -> LLMService:
    registry: ProviderRegistry[ChatModelProvider] = ProviderRegistry("llm")
    registry.register("p1", lambda: p1)  # type: ignore[arg-type,return-value]
    registry.register("p2", lambda: p2)  # type: ignore[arg-type,return-value]
    return LLMService(catalog(), registry, make_settings(**NO_ROLE_OVERRIDES))


class TestModelConstruction:
    def test_alias_resolves_to_the_providers_real_model_name(self) -> None:
        p1, p2 = ScriptedProvider("p1"), ScriptedProvider("p2")
        service(p1, p2).get_chat_model("default")
        assert p1.built[0]["model_name"] == "big-v1" and not p2.built

    def test_catalog_defaults_apply_when_the_caller_is_silent(self) -> None:
        p1, p2 = ScriptedProvider("p1"), ScriptedProvider("p2")
        service(p1, p2).get_chat_model("big")
        assert p1.built[0]["temperature"] == 0.7
        assert p1.built[0]["max_tokens"] == 2000

    def test_explicit_arguments_win_even_when_falsy(self) -> None:
        p1, p2 = ScriptedProvider("p1"), ScriptedProvider("p2")
        service(p1, p2).get_chat_model("big", temperature=0.0, max_tokens=1, streaming=False)
        assert (p1.built[0]["temperature"], p1.built[0]["max_tokens"]) == (0.0, 1)
        assert p1.built[0]["streaming"] is False

    def test_extra_kwargs_are_forwarded(self) -> None:
        p1, p2 = ScriptedProvider("p1"), ScriptedProvider("p2")
        service(p1, p2).get_chat_model("big", seed=7)
        assert p1.built[0]["seed"] == 7

    def test_unknown_model_fails_before_touching_any_provider(self) -> None:
        p1, p2 = ScriptedProvider("p1"), ScriptedProvider("p2")
        with pytest.raises(KeyError):
            service(p1, p2).get_chat_model("ghost")
        assert not p1.built and not p2.built

    def test_adapters_are_created_once_per_provider(self) -> None:
        created: list[str] = []
        registry: ProviderRegistry[ChatModelProvider] = ProviderRegistry("llm")

        def factory(name: str):  # type: ignore[no-untyped-def]
            def _make() -> ScriptedProvider:
                created.append(name)
                return ScriptedProvider(name)

            return _make

        registry.register("p1", factory("p1"))  # type: ignore[arg-type]
        registry.register("p2", factory("p2"))  # type: ignore[arg-type]
        svc = LLMService(catalog(), registry, make_settings(**NO_ROLE_OVERRIDES))
        for _ in range(3):
            svc.get_chat_model("big")
            svc.get_chat_model("small")
        assert sorted(created) == ["p1", "p2"]

    def test_capabilities_and_pricing_come_from_the_catalog(self) -> None:
        svc = service(ScriptedProvider("p1"), ScriptedProvider("p2"))
        assert svc.get_capabilities("default") == svc.catalog.get_capabilities("big")
        assert svc.get_pricing("default") == svc.catalog.get_pricing("big")


class TestRoles:
    def test_role_model_is_the_primary_of_the_chain(self) -> None:
        p1, p2 = ScriptedProvider("p1"), ScriptedProvider("p2")
        service(p1, p2).get_role_chat_model("generator")
        assert p1.built[0]["model_name"] == "big-v1"

    async def test_chain_has_one_member_per_model_in_order(self) -> None:
        p1, p2 = ScriptedProvider("p1"), ScriptedProvider("p2")
        chain = service(p1, p2).get_role_fallback_chain("generator")
        assert [m.name for m in chain.members] == ["big", "small", "backup"]  # type: ignore[attr-defined]
        assert chain.name == "role_chain_generator"

    async def test_failover_answers_from_the_next_model_and_reports_who(self) -> None:
        p1 = ScriptedProvider("p1", {"big-v1": [ConnectionError("provider down")]})
        p2 = ScriptedProvider("p2", {"small-v1": ["answer from small"]})
        chain = service(p1, p2).get_role_fallback_chain("generator")

        reply, used = await chain.execute(lambda m: m.ainvoke([HumanMessage(content="hi")]))

        assert reply.content == "answer from small"
        assert used.name == "small"  # type: ignore[attr-defined]  # observability: who answered

    async def test_all_models_down_raises_instead_of_hanging(self) -> None:
        err = ConnectionError("down")
        p1 = ScriptedProvider("p1", {"big-v1": [err]})
        p2 = ScriptedProvider("p2", {"small-v1": [err], "backup-v1": [err]})
        chain = service(p1, p2).get_role_fallback_chain("generator")
        with pytest.raises(RuntimeError, match="role_chain_generator"):
            await chain.execute(lambda m: m.ainvoke([HumanMessage(content="hi")]))

    async def test_changing_the_environment_changes_the_model_without_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        p1, p2 = ScriptedProvider("p1"), ScriptedProvider("p2")
        registry: ProviderRegistry[ChatModelProvider] = ProviderRegistry("llm")
        registry.register("p1", lambda: p1)  # type: ignore[arg-type,return-value]
        registry.register("p2", lambda: p2)  # type: ignore[arg-type,return-value]
        overridden = make_settings(**{**NO_ROLE_OVERRIDES, "LLM_ROLE_GENERATOR_PRIMARY": "small"})
        LLMService(catalog(), registry, overridden).get_role_chat_model("generator")
        assert p2.built[0]["model_name"] == "small-v1" and not p1.built


class TestShippedRegistry:
    def test_registers_the_five_documented_providers(self) -> None:
        assert create_default_llm_registry(make_settings()).available_providers() == [
            "anthropic",
            "gemini",
            "openai",
            "openai_compatible",
            "openrouter",
        ]

    def test_the_real_catalog_builds_real_models_offline(self) -> None:
        settings = make_settings(**KEYLESS, **NO_ROLE_OVERRIDES)
        svc = LLMService(
            ModelCatalog.load_from_yaml(YAML_PATH), create_default_llm_registry(settings), settings
        )
        model = svc.get_chat_model("gen-default")
        assert isinstance(model, ChatOpenAI) and model.model_name == "gpt-4o"

    def test_every_catalog_model_can_be_built(self) -> None:
        settings = make_settings(**KEYLESS, **NO_ROLE_OVERRIDES)
        cat = ModelCatalog.load_from_yaml(YAML_PATH)
        svc = LLMService(cat, create_default_llm_registry(settings), settings)
        for key in cat.config.models:
            svc.get_chat_model(key)  # must not raise

    def test_every_role_has_a_buildable_fallback_chain(self) -> None:
        settings = make_settings(**KEYLESS, **NO_ROLE_OVERRIDES)
        cat = ModelCatalog.load_from_yaml(YAML_PATH)
        svc = LLMService(cat, create_default_llm_registry(settings), settings)
        for role in cat.config.roles:
            assert svc.get_role_fallback_chain(role).members


class TestCatalogAgreesWithAdapters:
    """Pricing / capabilities live in two places (YAML and adapter heuristics). They must agree,
    or cost reports and capability-driven strategy selection are wrong."""

    @staticmethod
    def _mismatches(providers: set[str]) -> list[str]:
        settings = make_settings(**KEYLESS)
        registry = create_default_llm_registry(settings)
        cat = ModelCatalog.load_from_yaml(YAML_PATH)
        problems: list[str] = []
        for key, entry in cat.config.models.items():
            if entry.provider not in providers:
                continue
            adapter = registry.create(entry.provider)
            from_catalog = cat.get_capabilities(key)
            from_adapter = adapter.get_capabilities(entry.model_name)
            for field in (
                "supports_tools",
                "supports_json_schema",
                "supports_logprobs",
                "supports_vision",
                "context_window",
                "pricing",
            ):
                if getattr(from_catalog, field) != getattr(from_adapter, field):
                    problems.append(
                        f"{key}.{field}: catalog={getattr(from_catalog, field)} "
                        f"adapter={getattr(from_adapter, field)}"
                    )
        return problems

    def test_first_party_providers_agree(self) -> None:
        assert not self._mismatches({"openai", "anthropic"})

    def test_all_providers_agree(self) -> None:
        assert not self._mismatches({"openai", "anthropic", "openrouter", "openai_compatible"})
