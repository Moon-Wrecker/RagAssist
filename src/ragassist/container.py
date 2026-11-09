"""Application composition root and dependency injection container.

Coordinates configuration, platform adapters (storage, queues, providers),
and domain application services across bounded contexts following Hexagonal Architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from ragassist.platform.queue.sqs_adapter import InMemoryMessageQueue, SQSMessageQueue
from ragassist.platform.storage.ports import MessageQueue, ObjectStore
from ragassist.platform.storage.s3_adapter import InMemoryObjectStore, S3ObjectStore
from ragassist.shared.config.settings import Settings, get_settings


@dataclass
class Container:
    """Application dependency container providing singleton and factory access to services."""

    settings: Settings = field(default_factory=get_settings)
    _object_store: ObjectStore | None = None
    _message_queue: MessageQueue | None = None
    _decision_service: Any = None
    _retrieval_service: Any = None
    _assistant_graph: Any = None
    _checkpointer: Any = None

    @property
    def object_store(self) -> ObjectStore:
        """Resolve object store: S3 adapter in cloud/LocalStack mode, in-memory store in offline mode."""
        if self._object_store is None:
            if self.settings.USE_LOCALSTACK or self.settings.AWS_ACCESS_KEY_ID:
                try:
                    self._object_store = S3ObjectStore(settings=self.settings)
                except Exception:
                    self._object_store = InMemoryObjectStore()
            else:
                self._object_store = InMemoryObjectStore()
        return self._object_store

    @property
    def message_queue(self) -> MessageQueue:
        """Resolve message queue: SQS adapter in cloud/LocalStack mode, in-memory queue in offline mode."""
        if self._message_queue is None:
            if self.settings.USE_LOCALSTACK or self.settings.AWS_ACCESS_KEY_ID:
                try:
                    self._message_queue = SQSMessageQueue(settings=self.settings)
                except Exception:
                    self._message_queue = InMemoryMessageQueue()
            else:
                self._message_queue = InMemoryMessageQueue()
        return self._message_queue

    def get_decision_service(self) -> Any:
        """Resolve DecisionService singleton."""
        if self._decision_service is None:
            from ragassist.platform.decisions.service import build_decision_service

            self._decision_service = build_decision_service(self.settings)
        return self._decision_service

    def get_retrieval_service(self) -> Any:
        """Resolve configured RetrievalService facade."""
        if self._retrieval_service is None:
            try:
                from ragassist.modules.retrieval.application import DefaultRetrievalService
                from ragassist.modules.retrieval.fusion import HybridRetriever
                from ragassist.modules.retrieval.keyword_retriever import PgKeywordRetriever
                from ragassist.modules.retrieval.vector_retriever import PgVectorRetriever
                from ragassist.platform.embeddings.service import build_embedding_service
                from ragassist.platform.rerank.service import build_reranker
                from ragassist.shared.db.scoped import ScopedDatabase
                from ragassist.shared.db.session import get_session_factory

                session_factory = get_session_factory(self.settings)
                db = ScopedDatabase(session_factory)
                embedder = build_embedding_service(self.settings)
                dense = PgVectorRetriever(db=db, embedder=embedder)
                sparse = PgKeywordRetriever(db=db)
                hybrid = HybridRetriever(
                    dense=dense, sparse=sparse, rrf_k=self.settings.RETRIEVAL_RRF_K
                )
                reranker = build_reranker(self.settings)
                self._retrieval_service = DefaultRetrievalService(
                    retriever=hybrid, reranker=reranker
                )
            except Exception:
                from ragassist.modules.retrieval.application import DefaultRetrievalService

                class _StubRetriever:
                    async def search(self, *args: Any, **kwargs: Any) -> list[Any]:
                        return []

                self._retrieval_service = DefaultRetrievalService(retriever=_StubRetriever())
        return self._retrieval_service

    def get_assistant_graph(self, checkpointer: Any = None) -> Any:
        """Resolve compiled Assistant StateGraph."""
        if self._assistant_graph is None or checkpointer is not None:
            from langgraph.checkpoint.memory import MemorySaver

            import httpx
            from ragassist.modules.actions.adapters.saas_client import SaaSClient
            from ragassist.modules.actions.application import ToolRegistry
            from ragassist.modules.actions.tools import default_tools
            from ragassist.modules.assistant.graph.builder import build_graph
            from ragassist.platform.rerank.service import build_reranker_chain

            decision_svc = self.get_decision_service()
            retrieval_svc = self.get_retrieval_service()

            try:
                from ragassist.platform.llm.catalog import ModelCatalog
                from ragassist.platform.llm.service import LLMService, create_default_llm_registry

                cat = ModelCatalog.from_yaml(self.settings.MODELS_CONFIG_PATH)
                reg = create_default_llm_registry(self.settings)
                llm_svc = LLMService(cat, reg, self.settings)
                generator_tiers = {
                    "cheap": llm_svc.get_role_chat_model("generator_cheap"),
                    "strong": llm_svc.get_role_chat_model("generator_primary"),
                }
            except Exception:
                from ragassist.platform.llm.adapters.openai_adapter import OpenAIAdapter

                adapter = OpenAIAdapter(settings=self.settings)
                model = adapter.build_chat_model("gpt-4o-mini")
                generator_tiers = {
                    "cheap": model,
                    "strong": model,
                }

            reranker = build_reranker_chain(self.settings)
            saas = SaaSClient(http=httpx.AsyncClient(base_url=self.settings.MOCK_SAAS_BASE_URL))
            tools = ToolRegistry(default_tools(saas))
            cp = checkpointer or self._checkpointer or MemorySaver()
            self._checkpointer = cp

            compiled = build_graph(
                settings=self.settings,
                decision_service=decision_svc,
                generator_tiers=generator_tiers,
                retriever=getattr(retrieval_svc, "retriever", retrieval_svc),
                reranker=reranker,
                tools=tools,
                checkpointer=cp,
            )
            if checkpointer is None:
                self._assistant_graph = compiled
            return compiled
        return self._assistant_graph


@lru_cache(maxsize=1)
def get_container() -> Container:
    """Return the global application container singleton."""
    return Container()


container = get_container()
