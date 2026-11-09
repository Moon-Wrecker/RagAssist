"""Model catalog (config/models.yaml): schema, alias / role resolution, environment overrides.

Requirement (implementation plan section 2): adding or swapping a model is a configuration change,
never a code change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from support.settings import make_settings

from ragassist.platform.llm.catalog import ModelCatalog
from ragassist.platform.llm.catalog_models import ModelsFileConfig
from ragassist.platform.llm.service import create_default_llm_registry

YAML_PATH = Path(__file__).resolve().parents[4] / "config" / "models.yaml"
REQUIRED_ROLES = {"generator", "rewriter", "agent", "judge", "decider"}

NO_ROLE_OVERRIDES = {
    "LLM_ROLE_GENERATOR_PRIMARY": "",
    "LLM_ROLE_GENERATOR_FALLBACKS": "",
    "LLM_ROLE_REWRITER_PRIMARY": "",
    "LLM_ROLE_AGENT_PRIMARY": "",
    "LLM_ROLE_JUDGE_PRIMARY": "",
    "LLM_ROLE_DECIDER_FALLBACK": "",
}


def model(provider: str = "openai", name: str = "m", **extra: Any) -> dict[str, Any]:
    return {"provider": provider, "model_name": name, **extra}


def make_catalog(
    models: dict[str, Any] | None = None,
    aliases: dict[str, str] | None = None,
    roles: dict[str, Any] | None = None,
) -> ModelCatalog:
    data = {
        "providers": {"openai": {"adapter": "openai"}},
        "models": models or {"a": model(name="a"), "b": model(name="b"), "c": model(name="c")},
        "aliases": aliases or {},
        "roles": roles or {"generator": {"primary": "a", "fallbacks": ["b", "c"]}},
    }
    return ModelCatalog(ModelsFileConfig.model_validate(data))


@pytest.fixture(scope="module")
def shipped() -> ModelCatalog:
    return ModelCatalog.load_from_yaml(YAML_PATH)


@pytest.fixture(scope="module")
def raw_yaml() -> dict[str, Any]:
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))


class TestShippedConfigIntegrity:
    """The file we ship must be internally consistent, or the app fails at first use."""

    def test_loads_and_validates(self, shipped: ModelCatalog) -> None:
        assert shipped.config.models

    def test_defines_every_role_the_graph_needs(self, shipped: ModelCatalog) -> None:
        assert set(shipped.config.roles) >= REQUIRED_ROLES

    def test_every_model_references_a_declared_provider(self, shipped: ModelCatalog) -> None:
        declared = set(shipped.config.providers)
        undeclared = {
            k: m.provider for k, m in shipped.config.models.items() if m.provider not in declared
        }
        assert not undeclared

    def test_every_provider_adapter_is_registered(self, shipped: ModelCatalog) -> None:
        registry = create_default_llm_registry(make_settings())
        missing = [
            p.adapter
            for p in shipped.config.providers.values()
            if not registry.is_registered(p.adapter)
        ]
        assert not missing

    def test_every_alias_resolves_to_a_model(self, shipped: ModelCatalog) -> None:
        for alias in shipped.config.aliases:
            assert shipped.resolve_model_id(alias) in shipped.config.models

    def test_alias_names_do_not_shadow_model_keys(self, shipped: ModelCatalog) -> None:
        assert not set(shipped.config.aliases) & set(shipped.config.models)

    @pytest.mark.parametrize("role", sorted(REQUIRED_ROLES))
    def test_every_role_chain_resolves_without_overrides(
        self, shipped: ModelCatalog, role: str
    ) -> None:
        chain = shipped.resolve_role_chain(role, settings=make_settings(**NO_ROLE_OVERRIDES))
        assert chain and all(m in shipped.config.models for m in chain)

    def test_pricing_and_windows_are_sane(self, shipped: ModelCatalog) -> None:
        for key, m in shipped.config.models.items():
            assert m.pricing.input_cost_per_mtok >= 0, key
            assert m.pricing.output_cost_per_mtok >= 0, key
            assert m.context_window > m.max_output_tokens > 0, key

    def test_a_model_that_cannot_stream_or_call_tools_is_not_primary_for_the_agent_role(
        self, shipped: ModelCatalog
    ) -> None:
        primary = shipped.resolve_role_chain("agent", settings=make_settings(**NO_ROLE_OVERRIDES))[
            0
        ]
        caps = shipped.get_capabilities(primary)
        assert caps.supports_tools and caps.supports_streaming

    def test_no_secrets_in_the_file(self, raw_yaml: dict[str, Any]) -> None:
        text = YAML_PATH.read_text(encoding="utf-8").lower()
        for needle in ("sk-", "api_key:", "secret", "password"):
            assert needle not in text.replace("api_key_env:", ""), needle
        assert all(
            p.get("api_key_env", "").endswith("_KEY") or not p.get("api_key_env")
            for p in raw_yaml["providers"].values()
        )


class TestResolution:
    def test_alias_resolves_to_the_canonical_key(self) -> None:
        assert make_catalog(aliases={"fast": "a"}).resolve_model_id("fast") == "a"

    def test_canonical_key_resolves_to_itself(self) -> None:
        assert make_catalog().resolve_model_id("b") == "b"

    def test_whitespace_is_ignored(self) -> None:
        assert make_catalog(aliases={"fast": "a"}).resolve_model_id("  fast  ") == "a"

    def test_alias_chains_are_followed(self) -> None:
        assert make_catalog(aliases={"x": "y", "y": "z", "z": "a"}).resolve_model_id("x") == "a"

    def test_alias_loop_is_detected(self) -> None:
        with pytest.raises(ValueError, match="[Cc]ircular"):
            make_catalog(aliases={"x": "y", "y": "x"}).resolve_model_id("x")

    def test_self_referencing_alias_is_detected(self) -> None:
        with pytest.raises(ValueError, match="[Cc]ircular"):
            make_catalog(aliases={"x": "x"}).resolve_model_id("x")

    def test_unknown_model_lists_what_is_available(self) -> None:
        with pytest.raises(KeyError) as excinfo:
            make_catalog(aliases={"fast": "a"}).resolve_model_id("nope")
        assert "nope" in str(excinfo.value) and "fast" in str(excinfo.value)

    def test_alias_pointing_nowhere_is_an_error(self) -> None:
        with pytest.raises(KeyError):
            make_catalog(aliases={"x": "ghost"}).resolve_model_id("x")

    def test_capabilities_are_translated_from_the_file(self) -> None:
        cat = make_catalog(
            models={
                "a": model(
                    name="a",
                    context_window=1000,
                    max_output_tokens=100,
                    pricing={"input_cost_per_mtok": 1.5, "output_cost_per_mtok": 6.0},
                    capabilities={
                        "tool_calling": False,
                        "json_mode": True,
                        "vision": True,
                        "logprobs": True,
                        "streaming": False,
                    },
                )
            },
            roles={"generator": {"primary": "a"}},
        )
        caps = cat.get_capabilities("a")
        assert (caps.supports_tools, caps.supports_json_schema, caps.supports_vision) == (
            False,
            True,
            True,
        )
        assert (caps.supports_logprobs, caps.supports_streaming, caps.context_window) == (
            True,
            False,
            1000,
        )
        assert (caps.pricing.input_cost_per_mtok, caps.pricing.output_cost_per_mtok) == (1.5, 6.0)
        assert cat.get_pricing("a") == caps.pricing

    def test_role_lookup_is_case_and_whitespace_insensitive(self) -> None:
        assert make_catalog().get_role_mapping("  GENERATOR ").primary == "a"

    def test_unknown_role_lists_defined_roles(self) -> None:
        with pytest.raises(KeyError, match="generator"):
            make_catalog().get_role_mapping("poet")


class TestRoleChains:
    def test_yaml_roles_are_used_when_nothing_is_overridden(self) -> None:
        cat = make_catalog()
        assert cat.resolve_role_chain("generator", make_settings(**NO_ROLE_OVERRIDES)) == [
            "a",
            "b",
            "c",
        ]

    def test_environment_override_replaces_primary_and_fallbacks(self) -> None:
        settings = make_settings(
            LLM_ROLE_GENERATOR_PRIMARY="c", LLM_ROLE_GENERATOR_FALLBACKS="a, b"
        )
        assert make_catalog().resolve_role_chain("generator", settings) == ["c", "a", "b"]

    def test_override_may_use_aliases(self) -> None:
        cat = make_catalog(aliases={"fast": "c"})
        settings = make_settings(**{**NO_ROLE_OVERRIDES, "LLM_ROLE_GENERATOR_PRIMARY": "fast"})
        assert cat.resolve_role_chain("generator", settings)[0] == "c"

    def test_duplicates_are_removed_keeping_first_position(self) -> None:
        cat = make_catalog(roles={"generator": {"primary": "a", "fallbacks": ["b", "a", "b", "c"]}})
        assert cat.resolve_role_chain("generator", make_settings(**NO_ROLE_OVERRIDES)) == [
            "a",
            "b",
            "c",
        ]

    def test_alias_and_canonical_duplicates_collapse(self) -> None:
        cat = make_catalog(
            aliases={"alpha": "a"},
            roles={"generator": {"primary": "alpha", "fallbacks": ["a", "b"]}},
        )
        assert cat.resolve_role_chain("generator", make_settings(**NO_ROLE_OVERRIDES)) == ["a", "b"]

    def test_override_naming_an_unknown_model_fails_loudly(self) -> None:
        settings = make_settings(LLM_ROLE_GENERATOR_PRIMARY="does-not-exist")
        with pytest.raises(KeyError, match="does-not-exist"):
            make_catalog().resolve_role_chain("generator", settings)

    def test_stray_commas_and_spaces_in_fallback_list_are_tolerated(self) -> None:
        settings = make_settings(
            **{
                **NO_ROLE_OVERRIDES,
                "LLM_ROLE_GENERATOR_PRIMARY": "a",
                "LLM_ROLE_GENERATOR_FALLBACKS": " b ,, c ,",
            }
        )
        assert make_catalog().resolve_role_chain("generator", settings) == ["a", "b", "c"]

    def test_role_name_is_normalised(self) -> None:
        assert make_catalog().resolve_role_chain(" Generator ", make_settings(**NO_ROLE_OVERRIDES))

    def test_default_settings_do_not_shadow_the_yaml_roles(self, shipped: ModelCatalog) -> None:
        """Out of the box (no env overrides) the roles in models.yaml must be what runs.

        Settings currently defaults every LLM_ROLE_* to a non-empty value, which always wins, so
        e.g. the `rewriter` role (fast-default in YAML) silently uses the expensive generator model.
        """
        chain = shipped.resolve_role_chain("rewriter", make_settings())
        assert shipped.get_role_mapping("rewriter").primary == "fast-default"
        assert chain[0] == shipped.resolve_model_id("fast-default")


class TestLoading:
    def test_missing_file_is_a_clear_error(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="models.yaml"):
            ModelCatalog.load_from_yaml(tmp_path / "models.yaml")

    def test_unknown_field_on_a_model_is_rejected(self, tmp_path: Path) -> None:
        bad = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
        bad["models"]["gpt-4o"]["contxt_window"] = 5  # typo
        path = tmp_path / "models.yaml"
        path.write_text(yaml.safe_dump(bad), encoding="utf-8")
        with pytest.raises(ValidationError):
            ModelCatalog.load_from_yaml(path)

    @pytest.mark.parametrize(
        "patch",
        [
            {"pricing": {"input_cost_per_mtok": -1.0}},
            {"context_window": 0},
            {"max_output_tokens": -5},
            {"default_params": {"temperature": 9.0}},
        ],
        ids=["negative-price", "zero-window", "negative-output", "temperature-range"],
    )
    def test_invalid_numbers_are_rejected(self, patch: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            make_catalog(models={"a": model(name="a", **patch)})

    def test_roles_section_is_required(self) -> None:
        with pytest.raises(ValidationError):
            ModelsFileConfig.model_validate({"providers": {}, "models": {}})

    def test_empty_file_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "models.yaml"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ValidationError):
            ModelCatalog.load_from_yaml(path)
