"""Pydantic schemas for models.yaml parsing and catalog data structures."""

from pydantic import BaseModel, ConfigDict, Field
from ragassist.platform.llm.ports import ModelCapabilities, ModelPricing


class PricingConfig(BaseModel):
    """Token pricing configuration per million tokens in USD."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_cost_per_mtok: float = Field(default=0.0, ge=0.0)
    output_cost_per_mtok: float = Field(default=0.0, ge=0.0)

    def to_domain(self) -> ModelPricing:
        return ModelPricing(
            input_cost_per_mtok=self.input_cost_per_mtok,
            output_cost_per_mtok=self.output_cost_per_mtok,
        )


class CapabilitiesConfig(BaseModel):
    """Model feature support configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_calling: bool = Field(default=True)
    json_mode: bool = Field(default=True)
    vision: bool = Field(default=False)
    logprobs: bool = Field(default=False)
    streaming: bool = Field(default=True)

    def to_domain(self, context_window: int, pricing: ModelPricing) -> ModelCapabilities:
        return ModelCapabilities(
            supports_tools=self.tool_calling,
            supports_json_schema=self.json_mode,
            supports_streaming=self.streaming,
            supports_logprobs=self.logprobs,
            supports_vision=self.vision,
            context_window=context_window,
            pricing=pricing,
        )


class ModelParamsConfig(BaseModel):
    """Default inference parameters for a model."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: float | None = Field(default=None, gt=0.0)


class ModelDefinitionConfig(BaseModel):
    """Configuration for a specific registered model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model_name: str
    context_window: int = Field(default=128000, gt=0)
    max_output_tokens: int = Field(default=4096, gt=0)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    default_params: ModelParamsConfig = Field(default_factory=ModelParamsConfig)


class ProviderConfig(BaseModel):
    """Provider connection configuration."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    adapter: str
    api_key_env: str = ""
    base_url: str | None = None
    base_url_env: str | None = None
    default_headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=30.0, gt=0.0)


class RoleMappingConfig(BaseModel):
    """Configuration mapping a semantic role to primary and fallback models."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    primary: str
    fallbacks: list[str] = Field(default_factory=list)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)


class ModelsFileConfig(BaseModel):
    """Top-level schema for config/models.yaml."""

    model_config = ConfigDict(extra="ignore")

    version: str = "1.0"
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelDefinitionConfig]
    aliases: dict[str, str] = Field(default_factory=dict)
    roles: dict[str, RoleMappingConfig]
