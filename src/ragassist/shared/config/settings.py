"""Application settings (Pydantic Settings v2).

Every value comes from the environment (or a ``.env`` file); nothing is configured in code. ``.env.example`` is the
single documented template and ``ragassist init-env`` writes a working ``.env`` from it with freshly generated
secrets. A field without a default is required, so a missing variable fails at start-up with the variable's name
instead of silently falling back to a value that is committed to the repository. The only fields that default to
an empty string are the optional third-party API keys and overrides, where empty means "not configured".

RULE (AGENTS.md section 3.7): never add a default for a credential, a connection detail or any deployment value
here. Add the variable to ``.env.example`` instead.

Sources consulted (AGENTS.md section 3.5): pydantic-settings documentation (required fields, ``env_file``,
``model_validator``), the twelve-factor "config" rule, and OWASP guidance against hard-coded credentials.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Marker passed to SDK constructors that insist on a non-empty key when no provider key is configured. It is not a
#: credential: requests made with it are rejected by the provider, and the fallback chain moves on.
UNCONFIGURED_KEY = "unconfigured"

_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Central configuration for RagAssist."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application & Environment ---
    APP_NAME: str
    APP_ENV: Literal["development", "test", "staging", "production"]
    DEBUG: bool
    LOG_LEVEL: str
    API_V1_PREFIX: str
    SECRET_KEY: str = Field(min_length=16)
    ALLOWED_HOSTS: list[str]
    CORS_ORIGINS: list[str]

    # --- Database & Row-Level Security ---
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_APP_USER: str
    DB_APP_PASSWORD: str = Field(min_length=8)
    DB_ADMIN_USER: str
    DB_ADMIN_PASSWORD: str = Field(min_length=8)
    # Optional full-URL overrides (managed databases); empty means "build from the DB_* parts above".
    DATABASE_URL: str = ""
    DATABASE_ADMIN_URL: str = ""
    DB_POOL_SIZE: int
    DB_MAX_OVERFLOW: int
    DB_POOL_TIMEOUT: float
    # "postgres" wires the real runtime (Postgres repositories, LangGraph checkpointer, the assistant graph).
    # "memory" keeps the in-process stores and a canned assistant reply: the automated tests use it.
    PERSISTENCE_BACKEND: Literal["memory", "postgres"]

    # --- Security & JWT ---
    JWT_ALGORITHM: str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int
    DEV_AUTH_SECRET: str = Field(min_length=16)

    # --- Sign-in (workspace + email + password) ---
    # Lifetime of the access token returned by login/refresh; the refresh cookie renews it.
    AUTH_ACCESS_TOKEN_MINUTES: int = Field(ge=1)
    AUTH_REFRESH_TOKEN_DAYS: int = Field(ge=1)
    AUTH_INVITE_HOURS: int = Field(ge=1)
    AUTH_MIN_PASSPHRASE_LENGTH: int = Field(ge=8)
    # Send the refresh cookie over HTTPS only. Must be true behind TLS (staging, production).
    AUTH_COOKIE_SECURE: bool
    # Failed attempts allowed per account, and attempts allowed per client address, inside the window.
    AUTH_LOGIN_MAX_FAILURES: int = Field(ge=1)
    AUTH_LOGIN_MAX_PER_IP: int = Field(ge=1)
    AUTH_LOGIN_WINDOW_SECONDS: int = Field(ge=1)
    # Public origin of the web app; invite and password-reset links are built from it.
    WEB_BASE_URL: str

    # --- AWS & LocalStack ---
    AWS_REGION: str
    USE_LOCALSTACK: bool
    LOCALSTACK_ENDPOINT: str
    AWS_ACCESS_KEY_ID: str = Field(min_length=1)
    AWS_SECRET_ACCESS_KEY: str = Field(min_length=1)
    S3_BUCKET_DOCS: str
    SQS_QUEUE_INGEST: str
    SQS_QUEUE_INGEST_DLQ: str
    SECRETS_MANAGER_SECRET_NAME: str

    # --- Mock SaaS Integration ---
    MOCK_SAAS_BASE_URL: str
    MOCK_SAAS_TIMEOUT_SECONDS: float

    # --- Model Providers ---
    MODELS_CONFIG_PATH: str
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENAI_COMPATIBLE_BASE_URL: str
    OPENAI_COMPATIBLE_API_KEY: str = ""
    # When set, every LLM role uses this one model on the OpenAI-compatible endpoint (Ollama, vLLM, Gemini...).
    OPENAI_COMPATIBLE_MODEL: str = ""
    OPENAI_COMPATIBLE_EMBEDDING_MODEL: str

    LLM_ROLE_GENERATOR_PRIMARY: str = ""
    LLM_ROLE_GENERATOR_FALLBACKS: str = ""
    LLM_ROLE_REWRITER_PRIMARY: str = ""
    LLM_ROLE_AGENT_PRIMARY: str = ""
    LLM_ROLE_JUDGE_PRIMARY: str = ""
    LLM_ROLE_DECIDER_FALLBACK: str = ""

    # --- Embeddings & Vector Search ---
    EMBEDDING_PROVIDER: str
    EMBEDDING_MODEL: str
    EMBEDDING_DIMENSION: int
    EMBEDDING_BATCH_SIZE: int
    EMBEDDING_TIMEOUT_SECONDS: float
    EMBEDDING_FALLBACK_CHAIN: str
    SENTENCE_TRANSFORMERS_MODEL: str
    SENTENCE_TRANSFORMERS_DEVICE: str
    VECTOR_SEARCH_TOP_K: int
    VECTOR_SEARCH_ITERATIVE_SCAN: Literal["off", "relaxed_order", "strict_order"]

    # --- Keyword Search ---
    KEYWORD_SEARCH_BACKEND: str
    KEYWORD_SEARCH_TOP_K: int

    # --- Hybrid Retrieval & Reranker Chain ---
    RETRIEVAL_RRF_K: int
    RETRIEVAL_TOP_N: int
    RERANK_ENABLED: bool
    RERANKER_CHAIN: str
    RERANK_CROSS_ENCODER_MODEL: str
    RERANK_FLASHRANK_MODEL: str
    RERANK_TIMEOUT_MS: int

    # --- Chunking ---
    CHUNK_STRATEGY: str
    CHUNK_MAX_TOKENS: int
    CHUNK_OVERLAP_TOKENS: int
    CHUNK_MERGE_PEERS: bool
    CHUNK_SEMANTIC: bool
    CHUNK_PARENT_CHILD: bool

    # --- Decisions ---
    DECIDER_CHAIN: str
    ROUTER_DECIDER_CHAIN: str
    DECIDER_MIN_CONFIDENCE: float = Field(ge=0.0, le=1.0)
    DECIDER_TIMEOUT_MS: int
    ESCALATION_THRESHOLD: float = Field(ge=0.0, le=1.0)

    TYPESAFE_API_KEY: str = ""
    OPENAI_DECISIONS_API_KEY: str = ""
    STRANDS_DECIDER_ENDPOINT: str

    # --- Observability ---
    LANGSMITH_TRACING: bool
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str
    LANGSMITH_ENDPOINT: str
    PROMETHEUS_METRICS_ENABLED: bool

    # --- Worker ---
    WORKER_CONCURRENCY: int
    WORKER_MAX_RETRIES: int
    WORKER_VISIBILITY_TIMEOUT_SECONDS: int
    WORKER_POLL_WAIT_SECONDS: int

    # --- Live events stream (GET /v1/events) ---
    EVENTS_MAX_STREAMS_PER_USER: int = Field(ge=1)
    EVENTS_QUEUE_SIZE: int = Field(ge=1)

    @model_validator(mode="after")
    def _build_database_urls(self) -> Settings:
        """Compose the connection URLs from the parts so a password is configured in exactly one place."""
        target = f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{quote(self.DB_APP_USER, safe='')}:"
                f"{quote(self.DB_APP_PASSWORD, safe='')}@{target}"
            )
        if not self.DATABASE_ADMIN_URL:
            self.DATABASE_ADMIN_URL = (
                f"postgresql+asyncpg://{quote(self.DB_ADMIN_USER, safe='')}:"
                f"{quote(self.DB_ADMIN_PASSWORD, safe='')}@{target}"
            )
        return self

    @model_validator(mode="after")
    def _require_secure_cookie_over_tls(self) -> Settings:
        """A refresh cookie sent over plain HTTP can be stolen on the wire, so staging and production insist."""
        if self.APP_ENV in ("staging", "production") and not self.AUTH_COOKIE_SECURE:
            raise ValueError(f"AUTH_COOKIE_SECURE must be true in {self.APP_ENV}.")
        return self

    @model_validator(mode="after")
    def _reject_weak_signing_key(self) -> Settings:
        """Outside development and test the JWT signing key must be long and must not be a template value."""
        if self.APP_ENV in ("staging", "production"):
            key = self.SECRET_KEY.strip()
            if len(key) < _MIN_SECRET_LENGTH or key.lower().startswith(("change", "dev-", "your-")):
                raise ValueError(
                    f"SECRET_KEY must be at least {_MIN_SECRET_LENGTH} random characters in {self.APP_ENV}."
                )
        return self

    def __repr__(self) -> str:
        """Mask secret fields in repr() so logged Settings instances never leak credentials."""
        secret_fields = {
            "SECRET_KEY",
            "DEV_AUTH_SECRET",
            "DB_APP_PASSWORD",
            "DB_ADMIN_PASSWORD",
            "DATABASE_URL",
            "DATABASE_ADMIN_URL",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENROUTER_API_KEY",
            "OPENAI_COMPATIBLE_API_KEY",
            "TYPESAFE_API_KEY",
            "OPENAI_DECISIONS_API_KEY",
            "LANGSMITH_API_KEY",
        }
        parts = []
        for k in self.__class__.model_fields:
            val = getattr(self, k, None)
            if k in secret_fields and val:
                parts.append(f"{k}=SecretStr('**********')")
            else:
                parts.append(f"{k}={val!r}")
        return f"Settings({', '.join(parts)})"

    def model_dump_json(self, **kwargs: object) -> str:
        """Mask secret fields when serializing Settings to JSON."""
        import json

        data = self.model_dump()
        for k in (
            "SECRET_KEY",
            "DEV_AUTH_SECRET",
            "DB_APP_PASSWORD",
            "DB_ADMIN_PASSWORD",
            "DATABASE_URL",
            "DATABASE_ADMIN_URL",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENROUTER_API_KEY",
            "OPENAI_COMPATIBLE_API_KEY",
            "TYPESAFE_API_KEY",
            "OPENAI_DECISIONS_API_KEY",
            "LANGSMITH_API_KEY",
        ):
            if data.get(k):
                data[k] = "**********"
        return json.dumps(data)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton getter for application settings."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]  # every field is read from the environment
    return _settings
