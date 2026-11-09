"""Unit tests for Model Catalog, Schema Validation, Provider Registry, and LLMService."""

from pathlib import Path

import pytest
import yaml
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from ragassist.platform.llm.catalog import ModelCatalog
from ragassist.platform.llm.catalog_models import ModelsFileConfig
from ragassist.platform.llm.ports import ModelCapabilities, ModelPricing
from ragassist.platform.llm.service import LLMService, create_default_llm_registry
from ragassist.shared.config.settings import Settings


def test_models_yaml_syntax_and_schema_validation():
    """Verify that config/models.yaml is valid YAML and passes full Pydantic validation."""
    yaml_path = Path("config/models.yaml")
    assert yaml_path.exists(), "config/models.yaml must exist"

    with yaml_path.open("r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)

    config = ModelsFileConfig.model_validate(raw_data)
    assert config.version == "1.0"

    # Check required providers
    expected_providers = {"openai", "anthropic", "openrouter", "openai_compatible"}
    assert expected_providers.issubset(set(config.providers.keys()))

    # Check key models
    expected_models = {
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3-5-sonnet",
        "claude-3-5-haiku",
        "openrouter-llama-3.1-70b",
        "local-llama-3.1-8b",
    }
    assert expected_models.issubset(set(config.models.keys()))

    # Validate model definition constraints
    for model_id, model in config.models.items():
        assert model.context_window > 0, f"Model {model_id} context window must be > 0"
        assert model.max_output_tokens > 0, f"Model {model_id} max output tokens must be > 0"
        assert model.pricing.input_cost_per_mtok >= 0.0
        assert model.pricing.output_cost_per_mtok >= 0.0

    # Check required roles
    expected_roles = {"generator", "rewriter", "agent", "judge", "decider"}
    assert expected_roles.issubset(set(config.roles.keys()))


def test_model_catalog_alias_and_model_resolution():
    """Verify alias resolution recursively reaches canonical model keys."""
    catalog = ModelCatalog.load_from_yaml("config/models.yaml")

    assert catalog.resolve_model_id("gen-default") == "gpt-4o"
    assert catalog.resolve_model_id("fast-default") == "gpt-4o-mini"
    assert catalog.resolve_model_id("claude-sonnet") == "claude-3-5-sonnet"
    assert catalog.resolve_model_id("claude-haiku") == "claude-3-5-haiku"
    assert catalog.resolve_model_id("gpt-4o") == "gpt-4o"

    with pytest.raises(KeyError) as exc_info:
        catalog.resolve_model_id("non-existent-model-xyz")
    assert "Unknown model or alias" in str(exc_info.value)


def test_model_capabilities_and_pricing_conversion():
    """Verify conversion from YAML schema to domain ModelCapabilities and ModelPricing."""
    catalog = ModelCatalog.load_from_yaml("config/models.yaml")

    caps = catalog.get_capabilities("gpt-4o")
    assert isinstance(caps, ModelCapabilities)
    assert caps.supports_tools is True
    assert caps.tool_calling is True
    assert caps.supports_vision is True
    assert caps.vision is True
    assert caps.supports_logprobs is True
    assert caps.context_window == 128000

    pricing = catalog.get_pricing("gpt-4o")
    assert isinstance(pricing, ModelPricing)
    assert pricing.input_cost_per_mtok == 2.50
    assert pricing.output_cost_per_mtok == 10.00


def test_role_chain_resolution_with_settings_override():
    """Verify that resolve_role_chain resolves aliases and respects Settings overrides."""
    catalog = ModelCatalog.load_from_yaml("config/models.yaml")

    # Default role chain from YAML
    default_gen = catalog.resolve_role_chain("generator")
    assert default_gen[0] == "gpt-4o"
    assert "claude-3-5-sonnet" in default_gen

    # Custom settings override
    custom_settings = Settings(
        LLM_ROLE_GENERATOR_PRIMARY="claude-3-5-sonnet",
        LLM_ROLE_GENERATOR_FALLBACKS="gpt-4o-mini,local-llama-3.1-8b",
    )
    overridden_gen = catalog.resolve_role_chain("generator", settings=custom_settings)
    assert overridden_gen == ["claude-3-5-sonnet", "gpt-4o-mini", "local-llama-3.1-8b"]


def test_provider_registry_and_service_instantiation():
    """Verify default LLM provider registry registers all required adapters."""
    registry = create_default_llm_registry()
    available = registry.available_providers()

    assert "openai" in available
    assert "anthropic" in available
    assert "openrouter" in available
    assert "openai_compatible" in available

    openai_adapter = registry.create("openai")
    assert openai_adapter.name == "openai"


def test_llm_service_get_chat_model():
    """Verify LLMService.get_chat_model instantiates appropriate BaseChatModel."""
    catalog = ModelCatalog.load_from_yaml("config/models.yaml")
    registry = create_default_llm_registry()
    service = LLMService(catalog=catalog, registry=registry)

    # gpt-4o should instantiate ChatOpenAI
    openai_model = service.get_chat_model("gpt-4o", temperature=0.2, max_tokens=1000)
    assert isinstance(openai_model, ChatOpenAI)
    assert openai_model.model_name == "gpt-4o"
    assert openai_model.temperature == 0.2
    assert openai_model.max_tokens == 1000

    # claude-3-5-sonnet should instantiate ChatAnthropic
    anthropic_model = service.get_chat_model("claude-3-5-sonnet", temperature=0.1)
    assert isinstance(anthropic_model, ChatAnthropic)
    assert anthropic_model.model == "claude-3-5-sonnet-20241022"


def test_llm_service_role_fallback_chain():
    """Verify LLMService constructs ordered FallbackChain for a role."""
    catalog = ModelCatalog.load_from_yaml("config/models.yaml")
    registry = create_default_llm_registry()
    service = LLMService(catalog=catalog, registry=registry)

    chain = service.get_role_fallback_chain("generator")
    assert chain.name == "role_chain_generator"
    assert len(chain.members) >= 2
    # Primary member is gpt-4o
    assert isinstance(chain.members[0], ChatOpenAI)
