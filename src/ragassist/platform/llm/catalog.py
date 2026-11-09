"""Model catalog loader and capability resolver."""

from pathlib import Path
from typing import Any
import yaml

from ragassist.platform.llm.catalog_models import (
    ModelDefinitionConfig,
    ModelsFileConfig,
    RoleMappingConfig,
)
from ragassist.platform.llm.ports import ModelCapabilities, ModelPricing
from ragassist.shared.config.settings import Settings


class ModelCatalog:
    """Thread-safe catalog loaded from config/models.yaml."""

    def __init__(self, config: ModelsFileConfig) -> None:
        self._config = config
        self._models = config.models
        self._aliases = config.aliases
        self._roles = config.roles
        self._providers = config.providers

    @property
    def config(self) -> ModelsFileConfig:
        return self._config

    @classmethod
    def load_from_yaml(cls, path: str | Path = "config/models.yaml") -> "ModelCatalog":
        """Load and parse models configuration from YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Model catalog config file not found: {file_path.resolve()}")

        with file_path.open("r", encoding="utf-8") as f:
            raw_data: Any = yaml.safe_load(f)

        config = ModelsFileConfig.model_validate(raw_data)
        return cls(config)

    def resolve_pricing(self, model_or_alias: str, provider_name: str | None = None) -> ModelPricing:
        """Resolve pricing for a model name, alias, or provider family from the YAML catalog."""
        low = model_or_alias.strip().lower()
        # 1. Exact or case-insensitive key/alias match
        for k, v in self._aliases.items():
            if k.lower() == low:
                return self._models[v].pricing.to_domain()
        for k, m in self._models.items():
            if k.lower() == low or m.model_name.lower() == low:
                return m.pricing.to_domain()
        # 2. Substring match on model definitions for this provider
        for k, m in self._models.items():
            if provider_name and m.provider != provider_name:
                continue
            if k.lower() in low or low in m.model_name.lower():
                return m.pricing.to_domain()
        # 3. Family keyword match within provider's catalog models
        for k, m in self._models.items():
            if provider_name and m.provider != provider_name:
                continue
            for token in ("mini", "haiku", "sonnet", "llama", "mistral"):
                if token in low and token in k.lower():
                    return m.pricing.to_domain()
        # 4. Default to primary model of provider in catalog
        for m in self._models.values():
            if provider_name and m.provider == provider_name:
                return m.pricing.to_domain()
        return next(iter(self._models.values())).pricing.to_domain()

    def resolve_model_id(self, key_or_alias: str) -> str:
        """Resolve alias to canonical model key, or return key if already canonical."""
        target = key_or_alias.strip()
        visited = set()
        while target in self._aliases:
            if target in visited:
                raise ValueError(f"Circular alias loop detected for '{key_or_alias}'")
            visited.add(target)
            target = self._aliases[target]

        if target not in self._models:
            available = ", ".join(sorted(list(self._models.keys()) + list(self._aliases.keys())))
            raise KeyError(f"Unknown model or alias '{key_or_alias}'. Available: [{available}]")
        return target

    def get_model(self, key_or_alias: str) -> ModelDefinitionConfig:
        """Get canonical model definition."""
        canonical_id = self.resolve_model_id(key_or_alias)
        return self._models[canonical_id]

    def get_capabilities(self, key_or_alias: str) -> ModelCapabilities:
        """Get domain ModelCapabilities for a model."""
        model = self.get_model(key_or_alias)
        pricing = model.pricing.to_domain()
        return model.capabilities.to_domain(
            context_window=model.context_window,
            pricing=pricing,
        )

    def get_pricing(self, key_or_alias: str) -> ModelPricing:
        """Get domain ModelPricing for a model."""
        model = self.get_model(key_or_alias)
        return model.pricing.to_domain()

    def get_role_mapping(self, role: str) -> RoleMappingConfig:
        """Retrieve raw role configuration."""
        normalized_role = role.strip().lower()
        if normalized_role not in self._roles:
            available = ", ".join(sorted(self._roles.keys()))
            raise KeyError(f"Unknown role '{role}'. Defined roles: [{available}]")
        return self._roles[normalized_role]

    def resolve_role_chain(
        self,
        role: str,
        settings: Settings | None = None,
    ) -> list[str]:
        """Resolve ordered list of canonical model IDs for a role, with Settings override support."""
        normalized_role = role.strip().lower()
        role_cfg = self.get_role_mapping(normalized_role)

        # Check environment overrides if settings is provided
        primary_override: str | None = None
        fallbacks_override: list[str] | None = None

        if settings is not None:
            if normalized_role == "generator":
                if settings.LLM_ROLE_GENERATOR_PRIMARY and settings.LLM_ROLE_GENERATOR_PRIMARY.strip():
                    primary_override = settings.LLM_ROLE_GENERATOR_PRIMARY.strip()
                if settings.LLM_ROLE_GENERATOR_FALLBACKS and settings.LLM_ROLE_GENERATOR_FALLBACKS.strip():
                    parsed_fallbacks = [
                        f.strip() for f in settings.LLM_ROLE_GENERATOR_FALLBACKS.split(",") if f.strip()
                    ]
                    if parsed_fallbacks:
                        fallbacks_override = parsed_fallbacks
            elif normalized_role == "rewriter":
                if settings.LLM_ROLE_REWRITER_PRIMARY and settings.LLM_ROLE_REWRITER_PRIMARY.strip():
                    primary_override = settings.LLM_ROLE_REWRITER_PRIMARY.strip()
            elif normalized_role == "agent":
                if settings.LLM_ROLE_AGENT_PRIMARY and settings.LLM_ROLE_AGENT_PRIMARY.strip():
                    primary_override = settings.LLM_ROLE_AGENT_PRIMARY.strip()
            elif normalized_role == "judge":
                if settings.LLM_ROLE_JUDGE_PRIMARY and settings.LLM_ROLE_JUDGE_PRIMARY.strip():
                    primary_override = settings.LLM_ROLE_JUDGE_PRIMARY.strip()
            elif normalized_role == "decider":
                if settings.LLM_ROLE_DECIDER_FALLBACK and settings.LLM_ROLE_DECIDER_FALLBACK.strip():
                    primary_override = settings.LLM_ROLE_DECIDER_FALLBACK.strip()

        primary = primary_override or role_cfg.primary
        fallbacks = fallbacks_override if fallbacks_override is not None else role_cfg.fallbacks

        raw_chain = [primary, *fallbacks]
        # Resolve all aliases to canonical IDs and deduplicate preserving order
        resolved_chain: list[str] = []
        for item in raw_chain:
            canonical = self.resolve_model_id(item)
            if canonical not in resolved_chain:
                resolved_chain.append(canonical)

        if settings is not None:
            resolved_chain = [
                model_id
                for position, model_id in enumerate(resolved_chain)
                if position == 0 or self.is_model_configured(model_id, settings)
            ]
        return resolved_chain

    def is_model_configured(self, model_id: str, settings: Settings) -> bool:
        """False only for a model whose provider is optional (``skip_when_unconfigured``) and has no API key set."""
        model = self.get_model(model_id)
        provider = self._providers.get(model.provider)
        if provider is None or not provider.skip_when_unconfigured or not provider.api_key_env:
            return True
        return bool(str(getattr(settings, provider.api_key_env, "") or "").strip())
