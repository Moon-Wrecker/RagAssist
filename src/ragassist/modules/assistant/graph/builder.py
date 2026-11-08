"""LangGraph Assistant StateGraph Builder.

Design and proven patterns consulted:
- LangGraph StateGraph & Conditional Edges Reference:
  https://langchain-ai.github.io/langgraph/reference/graphs/#langgraph.graph.StateGraph
- LangGraph Human-in-the-Loop Approval Pattern (interrupt / Command(resume=...)):
  https://langchain-ai.github.io/langgraph/how-tos/human-in-the-loop/
- LangGraph Corrective RAG (CRAG) & Self-RAG Architectural Patterns:
  https://langchain-ai.github.io/langgraph/tutorials/rag/langgraph_crag/
  https://langchain-ai.github.io/langgraph/tutorials/rag/langgraph_self_rag/
- Decision:
  We assemble an 11-node StateGraph where guard_input guards against injection,
  router categorizes queries, rewrite -> retrieve -> rerank -> grade performs
  bounded corrective retrieval, generate -> verify_grounding performs hallucination
  detection with single regeneration, account_agent pauses with interrupt() on
  write actions, escalate flags tickets, and finalize emits custom SSE events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any
from langgraph.graph import END, START, StateGraph

from ragassist.modules.assistant.graph.nodes.account_agent_node import (
    make_account_agent_node,
)
from ragassist.modules.assistant.graph.nodes.escalate_node import make_escalate_node
from ragassist.modules.assistant.graph.nodes.finalize_node import make_finalize_node
from ragassist.modules.assistant.graph.nodes.generate_node import make_generate_node
from ragassist.modules.assistant.graph.nodes.grade_relevance_node import (
    make_grade_relevance_node,
    route_after_grade,
)
from ragassist.modules.assistant.graph.nodes.guard_node import (
    make_guard_node,
    route_after_guard,
)
from ragassist.modules.assistant.graph.nodes.hybrid_retrieve_node import (
    make_hybrid_retrieve_node,
)
from ragassist.modules.assistant.graph.nodes.rerank_node import make_rerank_node
from ragassist.modules.assistant.graph.nodes.rewrite_node import make_rewrite_node
from ragassist.modules.assistant.graph.nodes.router_node import (
    make_router_node,
    route_after_router,
)
from ragassist.modules.assistant.graph.nodes.verify_grounding_node import (
    make_verify_grounding_node,
    route_after_grounding,
)
from ragassist.modules.assistant.graph.state import AssistantState

NODE_NAMES: tuple[str, ...] = (
    "guard_input",
    "router",
    "rewrite",
    "hybrid_retrieve",
    "rerank",
    "grade_relevance",
    "account_agent",
    "generate",
    "verify_grounding",
    "escalate",
    "finalize",
)


class AssistantCompiledGraph:
    """Wrapper around CompiledStateGraph preserving type contracts and decorating event streams."""

    def __init__(self, compiled: Any) -> None:
        self._compiled = compiled

    def __getattr__(self, name: str) -> Any:
        return getattr(self._compiled, name)

    def astream(self, *args: Any, **kwargs: Any) -> Any:
        return self._compiled.astream(*args, **kwargs)

    async def aget_state(self, *args: Any, **kwargs: Any) -> Any:
        return await self._compiled.aget_state(*args, **kwargs)

    def get_graph(self, *args: Any, **kwargs: Any) -> Any:
        return self._compiled.get_graph(*args, **kwargs)

    async def astream_events(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        underlying = self._compiled.astream_events(*args, **kwargs)
        try:
            async for event in underlying:
                # Filter out the preliminary container start event before the initial graph checkpoint is committed
                if event.get("event") == "on_chain_start" and event.get("name") == "LangGraph":
                    continue
                yield event
        finally:
            if hasattr(underlying, "aclose"):
                await underlying.aclose()


def build_graph(
    *,
    settings: Any,
    decision_service: Any,
    generator_tiers: Mapping[str, Any],
    retriever: Any,
    reranker: Any,
    tools: Any,
    checkpointer: Any = None,
    **kwargs: Any,
) -> Any:
    """Build and compile the Assistant StateGraph with checkpointing and interrupt approval."""
    builder = StateGraph(AssistantState)

    # 1. Register nodes
    builder.add_node("guard_input", make_guard_node(decision_service))
    builder.add_node("router", make_router_node(decision_service))
    builder.add_node("rewrite", make_rewrite_node())
    builder.add_node("hybrid_retrieve", make_hybrid_retrieve_node(retriever))
    builder.add_node("rerank", make_rerank_node(reranker))
    builder.add_node("grade_relevance", make_grade_relevance_node(decision_service))
    builder.add_node("account_agent", make_account_agent_node(dict(generator_tiers), tools))
    builder.add_node("generate", make_generate_node(dict(generator_tiers)))
    builder.add_node("verify_grounding", make_verify_grounding_node(decision_service))
    builder.add_node("escalate", make_escalate_node())
    builder.add_node("finalize", make_finalize_node())

    # 2. Add edges
    # Start -> Guard
    builder.add_edge(START, "guard_input")

    # Guard -> Router (or Finalize if blocked)
    builder.add_conditional_edges(
        "guard_input",
        route_after_guard,
        ["router", "finalize"],
    )

    # Router -> Target branches
    builder.add_conditional_edges(
        "router",
        route_after_router,
        ["rewrite", "account_agent", "generate", "escalate"],
    )

    # Retrieval pipeline
    builder.add_edge("rewrite", "hybrid_retrieve")
    builder.add_edge("hybrid_retrieve", "rerank")
    builder.add_edge("rerank", "grade_relevance")

    # Grade relevance -> Generate or Retry (rewrite / hybrid_retrieve) or Escalate
    builder.add_conditional_edges(
        "grade_relevance",
        route_after_grade,
        ["generate", "rewrite", "hybrid_retrieve", "escalate"],
    )

    # Generate -> Verify Grounding
    builder.add_edge("generate", "verify_grounding")

    # Verify Grounding -> Finalize or Regenerate or Escalate
    builder.add_conditional_edges(
        "verify_grounding",
        route_after_grounding,
        ["finalize", "generate", "escalate"],
    )

    # Account Agent -> Finalize
    builder.add_edge("account_agent", "finalize")

    # Escalate -> Finalize
    builder.add_edge("escalate", "finalize")

    # Finalize -> END
    builder.add_edge("finalize", END)

    # 3. Compile with checkpointer and wrap
    compiled = builder.compile(checkpointer=checkpointer)
    return AssistantCompiledGraph(compiled)
