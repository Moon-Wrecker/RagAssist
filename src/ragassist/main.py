"""FastAPI application factory for RagAssist.

Consulted References:
- FastAPI Application Factory & Modular Routers:
  https://fastapi.tiangolo.com/tutorial/bigger-applications/
- OpenAPI Metadata & Tags:
  https://fastapi.tiangolo.com/tutorial/metadata/
- Prometheus Metrics & Request Timing:
  https://prometheus.io/docs/instrumenting/exposition_formats/
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ragassist.modules.assistant.api.router import router as assistant_router
from ragassist.modules.escalation.api.router import router as escalation_router
from ragassist.modules.identity.api.router import router as auth_router
from ragassist.modules.knowledge.api.router import router as knowledge_router
from ragassist.shared.config.settings import get_settings
from ragassist.shared.observability.logging import configure_logging
from ragassist.shared.observability.metrics import setup_observability
from ragassist.shared.security.rate_limiter import RateLimitMiddleware

TAGS_METADATA = [
    {
        "name": "System",
        "description": "System health check and diagnostic endpoints.",
    },
    {
        "name": "Observability",
        "description": "Prometheus metrics exposition and telemetry.",
    },
    {
        "name": "Authentication",
        "description": "JWT authentication token issuance for development and testing.",
    },
    {
        "name": "Knowledge",
        "description": "Tenant document ingestion, listing, re-indexing, and deletion.",
    },
    {
        "name": "Assistant",
        "description": "Conversations, SSE streaming generation, and human-in-the-loop action decisions.",
    },
    {
        "name": "Escalation",
        "description": "Customer conversation escalations, human agent replies, and ticket resolution.",
    },
]


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(log_level=settings.LOG_LEVEL, json_format=settings.APP_ENV == "production")

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Production-Ready Multi-Tenant Enterprise RAG Assistant with LangGraph, "
            "Server-Sent Events streaming, and Human-in-the-Loop decision governance."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=TAGS_METADATA,
    )

    # Middleware pipeline
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)

    # Observability & Metrics (/metrics & X-Process-Time)
    setup_observability(app)

    @app.get("/healthz", tags=["System"])
    async def healthz() -> dict[str, str]:
        """Health check probe endpoint."""
        return {"status": "ok", "app": settings.APP_NAME}

    # Register module routers with API_V1_PREFIX (/v1)
    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    app.include_router(knowledge_router, prefix=settings.API_V1_PREFIX)
    app.include_router(assistant_router, prefix=settings.API_V1_PREFIX)
    app.include_router(escalation_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
