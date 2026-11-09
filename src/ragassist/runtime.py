"""Runtime composition root for the PostgreSQL-backed application.

Goal: turn configuration into one running object graph (database, object store, queue, model services, retrieval,
tools, LangGraph checkpointer and the compiled assistant graph) that the HTTP layer and the worker share. Tests keep
using the in-memory stores; this module is only started when ``PERSISTENCE_BACKEND=postgres``.

Sources consulted (AGENTS.md section 3.5):
* LangGraph ``AsyncPostgresSaver`` (langgraph-checkpoint-postgres): needs a psycopg ``AsyncConnectionPool`` opened
  with ``autocommit=True``, ``prepare_threshold=0`` and ``row_factory=dict_row``; tables come from ``setup()``,
  which ``ragassist db upgrade`` runs once with the owner role.
* psycopg 3 async on Windows: the default ProactorEventLoop is unsupported, so this fails fast with a clear message.
* SQLAlchemy 2.0 ``create_async_engine`` / ``async_sessionmaker``; ``ScopedDatabase`` applies the RLS tenant context.
* LangChain ``bind_tools`` and ``with_fallbacks`` for the tool-calling account agent.

Design decisions: every adapter is built through the existing registries (``ProviderRegistry``/``FallbackChain``),
so no model name or key is hard-coded here; a model that cannot be constructed (for example a missing key) is
skipped instead of failing start-up, and start-up fails only if no model is left.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ragassist.modules.actions.adapters.saas_client import SaaSClient
from ragassist.modules.actions.application import ToolRegistry, ToolSpec
from ragassist.modules.actions.tools import default_tools
from ragassist.modules.assistant.adapters.persistence import (
    PostgresAuditRepository,
    PostgresConversationStore,
)
from ragassist.modules.assistant.graph.builder import build_graph
from ragassist.modules.escalation.adapters.helpdesk import HelpdeskClient
from ragassist.modules.knowledge.adapters.persistence.repositories import (
    PostgresIngestionRepository,
    PostgresKnowledgeStore,
)
from ragassist.modules.retrieval.fusion import HybridRetriever
from ragassist.modules.retrieval.keyword_retriever import KeywordRetriever
from ragassist.modules.retrieval.vector_retriever import VectorRetriever
from ragassist.platform.decisions.service import build_decision_service
from ragassist.platform.embeddings.service import EmbeddingService, build_embedding_service
from ragassist.platform.llm.catalog import ModelCatalog
from ragassist.platform.llm.catalog_models import ModelDefinitionConfig
from ragassist.platform.llm.service import LLMService, create_default_llm_registry
from ragassist.platform.queue.sqs_adapter import SQSMessageQueue
from ragassist.platform.rerank.service import build_reranker_chain
from ragassist.platform.storage.s3_adapter import S3ObjectStore
from ragassist.shared.config.settings import Settings, get_settings
from ragassist.shared.db.scoped import ScopedDatabase
from ragassist.shared.db.session import get_engine, get_session_factory
from ragassist.shared.security.jwt import Principal, create_access_token

logger = structlog.get_logger(__name__)

HIDDEN_TOOLS = frozenset({"query_dataset", "get_invoices"})  # stub tool and a duplicate alias of list_invoices
CUSTOM_MODEL_KEY = "custom-default"


class DeferredQueue:
    """Queue facade whose sends wait for the surrounding database transaction to commit.

    The upload use case enqueues inside its transaction; sending before the commit would let the worker receive a
    message whose job row is not visible yet. Outside a transaction a send is immediate.
    """

    def __init__(self, queue: Any, database: ScopedDatabase) -> None:
        self._queue = queue
        self._database = database

    async def send_message(
        self, queue_name: str, message_body: dict[str, Any], delay_seconds: int = 0
    ) -> str:
        async def _send() -> None:
            await self._queue.send_message(queue_name, message_body, delay_seconds)

        await self._database.defer_until_commit(_send)
        return "queued"

    async def receive_messages(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return await self._queue.receive_messages(*args, **kwargs)

    async def delete_message(self, *args: Any, **kwargs: Any) -> bool:
        return await self._queue.delete_message(*args, **kwargs)


@dataclass
class Runtime:
    """Everything the HTTP layer and the worker need, built once at start-up."""

    settings: Settings
    database: ScopedDatabase
    session_factory: async_sessionmaker[AsyncSession]
    knowledge: PostgresKnowledgeStore
    ingestion: PostgresIngestionRepository
    conversations: PostgresConversationStore
    audit: PostgresAuditRepository
    object_store: Any
    raw_queue: Any
    queue: DeferredQueue
    embeddings: EmbeddingService
    retriever: HybridRetriever
    reranker: Any
    tools: ToolRegistry
    helpdesk: HelpdeskClient
    graph: Any
    _closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        for closer in reversed(self._closers):
            try:
                await closer()
            except Exception as exc:  # noqa: BLE001
                logger.warning("runtime.close_failed", error=str(exc))
        self._closers.clear()


_runtime: Runtime | None = None


def active_runtime() -> Runtime | None:
    """The started runtime, or ``None`` when the in-memory backend is in use."""
    return _runtime


async def start_runtime(settings: Settings | None = None) -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = await build_runtime(settings or get_settings())
    return _runtime


async def stop_runtime() -> None:
    global _runtime
    if _runtime is not None:
        await _runtime.aclose()
        _runtime = None


# --------------------------------------------------------------------------------------------------
# Building blocks (each is importable on its own so the worker and the CLI reuse them)
# --------------------------------------------------------------------------------------------------
def psycopg_conninfo(database_url: str) -> str:
    """Translate a SQLAlchemy asyncpg URL into the libpq URL psycopg expects."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def build_object_store_and_queue(settings: Settings) -> tuple[Any, Any]:
    return S3ObjectStore(settings), SQSMessageQueue(settings)


def catalog_for(settings: Settings) -> tuple[ModelCatalog, Settings]:
    """Load the model catalog; ``OPENAI_COMPATIBLE_MODEL`` points every role at one local/compatible model."""
    catalog = ModelCatalog.load_from_yaml(settings.MODELS_CONFIG_PATH)
    custom = settings.OPENAI_COMPATIBLE_MODEL.strip()
    if not custom:
        return catalog, settings
    catalog.config.models[CUSTOM_MODEL_KEY] = ModelDefinitionConfig(
        provider="openai_compatible", model_name=custom, context_window=32_768, max_output_tokens=2048
    )
    overridden = settings.model_copy(
        update={
            "LLM_ROLE_GENERATOR_PRIMARY": CUSTOM_MODEL_KEY,
            "LLM_ROLE_GENERATOR_FALLBACKS": CUSTOM_MODEL_KEY,
            "LLM_ROLE_REWRITER_PRIMARY": CUSTOM_MODEL_KEY,
            "LLM_ROLE_AGENT_PRIMARY": CUSTOM_MODEL_KEY,
            "LLM_ROLE_JUDGE_PRIMARY": CUSTOM_MODEL_KEY,
            "LLM_ROLE_DECIDER_FALLBACK": CUSTOM_MODEL_KEY,
        }
    )
    return catalog, overridden


def _role_models(llm: LLMService, role: str, settings: Settings) -> list[Any]:
    models: list[Any] = []
    for model_id in llm.catalog.resolve_role_chain(role, settings=settings):
        try:
            models.append(llm.get_chat_model(model_id))
        except Exception as exc:  # noqa: BLE001 - a missing key or SDK must not take the app down
            logger.warning("runtime.model_unavailable", role=role, model=model_id, error=str(exc))
    if not models:
        raise RuntimeError(
            f"No chat model could be built for role '{role}'. Set a provider key (OPENAI_API_KEY, "
            "ANTHROPIC_API_KEY, OPENROUTER_API_KEY) or OPENAI_COMPATIBLE_MODEL for a local server."
        )
    return models


def _tool_schemas(tools: ToolRegistry) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["input_schema"] or {"type": "object", "properties": {}},
            },
        }
        for spec in tools.schemas()
    ]


def _with_tools(models: list[Any], schemas: list[dict[str, Any]]) -> Any:
    bound = [m.bind_tools(schemas) for m in models]
    return bound[0].with_fallbacks(bound[1:]) if len(bound) > 1 else bound[0]


def build_tool_registry(
    settings: Settings, audit: PostgresAuditRepository, http: httpx.AsyncClient
) -> ToolRegistry:
    """SaaS tools wrapped with per-call token minting and an audit row for every execution.

    The graph state carries the principal without its raw JWT (so no credential lands in a checkpoint); each call
    mints a short-lived token for the verified user, which is what the SaaS service authenticates.
    """
    saas = SaaSClient(http)

    def wrap(spec: ToolSpec) -> ToolSpec:
        async def handler(principal: Principal, arguments: dict[str, Any]) -> Any:
            token = create_access_token(principal.user_id, principal.tenant_id, principal.role)
            authenticated = replace(principal, raw_token=token)
            try:
                result = await spec.handler(authenticated, arguments)
            except Exception as exc:
                await audit.record(
                    tenant_id=principal.tenant_id,
                    user_id=principal.user_id,
                    tool=spec.name,
                    arguments=arguments,
                    status="failed",
                    reason=str(exc)[:500],
                )
                raise
            await audit.record(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                tool=spec.name,
                arguments=arguments,
                status="executed",
                result=result,
            )
            return result

        return replace(spec, handler=handler)

    return ToolRegistry([wrap(s) for s in default_tools(saas) if s.name not in HIDDEN_TOOLS])


async def build_checkpointer(settings: Settings, closers: list[Callable[[], Awaitable[None]]]) -> Any:
    """LangGraph Postgres checkpointer on its own psycopg pool (the saver cannot share the SQLAlchemy engine)."""
    if sys.platform == "win32" and type(asyncio.get_running_loop()).__name__ == "ProactorEventLoop":
        raise RuntimeError(
            "psycopg's async mode does not run on Windows' default ProactorEventLoop. Start the app with "
            "`ragassist serve` (it selects the selector loop) or run it in Docker."
        )
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(
        conninfo=psycopg_conninfo(settings.DATABASE_URL),
        max_size=max(4, settings.DB_POOL_SIZE // 2),
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    await pool.open(wait=True, timeout=15)
    closers.append(pool.close)
    from ragassist.modules.assistant.graph.serde import checkpoint_serde

    return AsyncPostgresSaver(pool, serde=checkpoint_serde())  # type: ignore[arg-type]


async def build_runtime(settings: Settings) -> Runtime:
    closers: list[Callable[[], Awaitable[None]]] = []

    engine: AsyncEngine = get_engine(settings)
    closers.append(engine.dispose)
    session_factory = get_session_factory(settings)
    database = ScopedDatabase(session_factory)

    object_store, raw_queue = build_object_store_and_queue(settings)
    await ensure_aws_resources(settings)

    catalog, llm_settings = catalog_for(settings)
    llm = LLMService(catalog, create_default_llm_registry(llm_settings), llm_settings)
    embeddings = build_embedding_service(settings)
    decisions = build_decision_service(settings, llm_service=llm, embedding_service=embeddings)
    reranker = build_reranker_chain(settings)

    retriever = HybridRetriever(
        dense=VectorRetriever(embeddings, session_factory),  # type: ignore[arg-type]
        sparse=KeywordRetriever(session_factory),  # type: ignore[arg-type]
        rrf_k=settings.RETRIEVAL_RRF_K,
    )

    audit = PostgresAuditRepository(database)
    http = httpx.AsyncClient(
        base_url=settings.MOCK_SAAS_BASE_URL, timeout=settings.MOCK_SAAS_TIMEOUT_SECONDS
    )
    closers.append(http.aclose)
    tools = build_tool_registry(settings, audit, http)

    strong = _role_models(llm, "generator", llm_settings)
    cheap = _role_models(llm, "rewriter", llm_settings)
    schemas = _tool_schemas(tools)
    agent_strong = _role_models(llm, "agent", llm_settings)
    checkpointer = await build_checkpointer(settings, closers)

    graph = build_graph(
        settings=settings,
        decision_service=decisions,
        generator_tiers={"strong": strong, "cheap": cheap},
        agent_tiers={"strong": _with_tools(agent_strong, schemas), "cheap": _with_tools(cheap, schemas)},
        retriever=retriever,
        reranker=reranker,
        tools=tools,
        checkpointer=checkpointer,
    )

    logger.info("runtime.started", persistence=settings.PERSISTENCE_BACKEND)
    return Runtime(
        settings=settings,
        database=database,
        session_factory=session_factory,
        knowledge=PostgresKnowledgeStore(database),
        ingestion=PostgresIngestionRepository(database),
        conversations=PostgresConversationStore(database),
        audit=audit,
        object_store=object_store,
        raw_queue=raw_queue,
        queue=DeferredQueue(raw_queue, database),
        embeddings=embeddings,
        retriever=retriever,
        reranker=reranker,
        tools=tools,
        helpdesk=HelpdeskClient(http),
        graph=graph,
        _closers=closers,
    )


async def ensure_aws_resources(settings: Settings) -> None:
    """Create the bucket and queues on LocalStack when they are missing (a no-op against real AWS)."""
    if not settings.USE_LOCALSTACK:
        return
    import aioboto3

    session = aioboto3.Session(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    endpoint = {"endpoint_url": settings.LOCALSTACK_ENDPOINT}
    try:
        async with session.client("s3", **endpoint) as s3:
            try:
                await s3.head_bucket(Bucket=settings.S3_BUCKET_DOCS)
            except Exception:  # noqa: BLE001
                await s3.create_bucket(Bucket=settings.S3_BUCKET_DOCS)
        async with session.client("sqs", **endpoint) as sqs:
            await sqs.create_queue(QueueName=settings.SQS_QUEUE_INGEST_DLQ)
            await sqs.create_queue(QueueName=settings.SQS_QUEUE_INGEST)
    except Exception as exc:  # noqa: BLE001
        logger.warning("runtime.aws_bootstrap_failed", error=str(exc))
