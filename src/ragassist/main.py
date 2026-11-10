"""FastAPI application factory for RagAssist.

Consulted References:
- FastAPI Application Factory & Modular Routers:
  https://fastapi.tiangolo.com/tutorial/bigger-applications/
- OpenAPI Metadata & Tags:
  https://fastapi.tiangolo.com/tutorial/metadata/
- Prometheus Metrics & Request Timing:
  https://prometheus.io/docs/instrumenting/exposition_formats/
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ragassist.modules.assistant.api.router import router as assistant_router
from ragassist.modules.escalation.api.router import router as escalation_router
from ragassist.modules.identity.api.router import router as auth_router
from ragassist.modules.identity.api.team_router import router as team_router
from ragassist.modules.knowledge.api.router import router as knowledge_router
from ragassist.modules.retrieval.api.router import router as retrieval_router
from ragassist.platform.events.router import router as events_router
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
        "description": "Sign-in with workspace, email and password; refresh, sign-out, invite links.",
    },
    {
        "name": "Team",
        "description": "Workspace administrators manage members, roles, invitations and reset links.",
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
        "name": "Retrieval",
        "description": "Passages behind citations.",
    },
    {
        "name": "Events",
        "description": "Live change notifications (SSE): ids only, filtered by tenant, owner and role.",
    },
    {
        "name": "Escalation",
        "description": "Customer conversation escalations, human agent replies, and ticket resolution.",
    },
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start the PostgreSQL runtime (pools, checkpointer, graph, events listener) when PERSISTENCE_BACKEND=postgres."""
    from ragassist.modules.assistant.application.turns import drain
    from ragassist.platform.cache import shutdown_cache
    from ragassist.shared.observability.tracing import configure_langsmith, shutdown_tracing

    settings = get_settings()
    configure_langsmith(settings)
    if settings.PERSISTENCE_BACKEND != "postgres":
        try:
            yield
        finally:
            await drain()
            await shutdown_tracing()
            await shutdown_cache()
        return
    from ragassist.runtime import start_runtime, stop_runtime

    await start_runtime(settings)
    try:
        yield
    finally:
        await drain()  # finish in-flight assistant turns before the pools they use close
        await shutdown_tracing()  # then send what the traces still hold
        await stop_runtime()
        await shutdown_cache()  # the Redis pool, when there is one


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
        lifespan=lifespan,
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
    app.include_router(team_router, prefix=settings.API_V1_PREFIX)
    app.include_router(knowledge_router, prefix=settings.API_V1_PREFIX)
    app.include_router(assistant_router, prefix=settings.API_V1_PREFIX)
    app.include_router(escalation_router, prefix=settings.API_V1_PREFIX)
    app.include_router(retrieval_router, prefix=settings.API_V1_PREFIX)
    app.include_router(events_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
