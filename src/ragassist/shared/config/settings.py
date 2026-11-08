"""Application Settings using Pydantic Settings v2.

Every setting is synchronized with .env.example and AGENTS.md.
"""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for RagAssist."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application & Environment ---
    APP_NAME: str = "RagAssist"
    APP_ENV: Literal["development", "test", "staging", "production"] = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/v1"
    SECRET_KEY: str = "<redacted>"
    ALLOWED_HOSTS: list[str] = ["*"]
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
    ]

    # --- Database & Row-Level Security ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://app_user:<redacted>@localhost:5432/ragassist"
    )
    DATABASE_ADMIN_URL: str = (
        "postgresql+asyncpg://postgres:<redacted>@localhost:5432/ragassist"
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: float = 30.0

    # --- Security & JWT ---
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    DEV_AUTH_SECRET: str = "<redacted>"

    # --- AWS & LocalStack ---
    AWS_REGION: str = "us-east-1"
    USE_LOCALSTACK: bool = True
    LOCALSTACK_ENDPOINT: str = "http://localhost:4566"
    AWS_ACCESS_KEY_ID: str = "test"
    AWS_SECRET_ACCESS_KEY: str = "test"
    S3_BUCKET_DOCS: str = "ragassist-docs"
    SQS_QUEUE_INGEST: str = "ragassist-ingest"
    SQS_QUEUE_INGEST_DLQ: str = "ragassist-ingest-dlq"
    SECRETS_MANAGER_SECRET_NAME: str = "ragassist/config"

    # --- Mock SaaS Integration ---
    MOCK_SAAS_BASE_URL: str = "http://localhost:8001"
    MOCK_SAAS_TIMEOUT_SECONDS: float = 10.0

    # --- Model Providers ---
    MODELS_CONFIG_PATH: str = "config/models.yaml"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENAI_COMPATIBLE_BASE_URL: str = "http://localhost:11434/v1"
    OPENAI_COMPATIBLE_API_KEY: str = "ollama"

    LLM_ROLE_GENERATOR_PRIMARY: str = ""
    LLM_ROLE_GENERATOR_FALLBACKS: str = ""
    LLM_ROLE_REWRITER_PRIMARY: str = ""
    LLM_ROLE_AGENT_PRIMARY: str = ""
    LLM_ROLE_JUDGE_PRIMARY: str = ""
    LLM_ROLE_DECIDER_FALLBACK: str = ""

    # --- Embeddings & Vector Search ---
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_BATCH_SIZE: int = 64
    EMBEDDING_TIMEOUT_SECONDS: float = 15.0
    EMBEDDING_FALLBACK_CHAIN: str = "openai,sentence_transformers"
    SENTENCE_TRANSFORMERS_MODEL: str = "all-MiniLM-L6-v2"
    SENTENCE_TRANSFORMERS_DEVICE: str = "auto"
    VECTOR_SEARCH_TOP_K: int = 30
    VECTOR_SEARCH_ITERATIVE_SCAN: str = "relaxed_order"

    # --- Keyword Search ---
    KEYWORD_SEARCH_BACKEND: str = "fts"
    KEYWORD_SEARCH_TOP_K: int = 30

    # --- Hybrid Retrieval & Reranker Chain ---
    RETRIEVAL_RRF_K: int = 60
    RETRIEVAL_TOP_N: int = 6
    RERANK_ENABLED: bool = True
    RERANKER_CHAIN: str = "cross_encoder,flashrank,none"
    RERANK_CROSS_ENCODER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RERANK_FLASHRANK_MODEL: str = "ms-marco-TinyBERT-L-2-v2"
    RERANK_TIMEOUT_MS: int = 1500

    # --- Chunking ---
    CHUNK_STRATEGY: str = "hybrid"
    CHUNK_MAX_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 64
    CHUNK_MERGE_PEERS: bool = True
    CHUNK_SEMANTIC: bool = False
    CHUNK_PARENT_CHILD: bool = False

    # --- Decisions ---
    DECIDER_CHAIN: str = "openai_decisions,jev,llm_structured,rules"
    ROUTER_DECIDER_CHAIN: str = "semantic_router,openai_decisions,llm_structured,rules"
    DECIDER_MIN_CONFIDENCE: float = 0.70
    DECIDER_TIMEOUT_MS: int = 1000
    ESCALATION_THRESHOLD: float = 0.65

    TYPESAFE_API_KEY: str = ""
    OPENAI_DECISIONS_API_KEY: str = ""
    STRANDS_DECIDER_ENDPOINT: str = "http://localhost:8002/v1/decide"

    # --- Observability ---
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "ragassist-dev"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    PROMETHEUS_METRICS_ENABLED: bool = True

    # --- Worker ---
    WORKER_CONCURRENCY: int = 4
    WORKER_MAX_RETRIES: int = 3
    WORKER_VISIBILITY_TIMEOUT_SECONDS: int = 120
    WORKER_POLL_WAIT_SECONDS: int = 10


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton getter for application settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

