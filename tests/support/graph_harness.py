"""Harness for the LangGraph assistant (plan section 7, scenarios G1-G22).

Each scenario builds the graph from fakes and drives one conversation turn. ``run_turn`` returns the
node path (the order nodes ran in), the final state and the raw updates, so every scenario asserts
exactly which path the graph took. ``ScriptedDecider`` answers each named question (route, safety,
relevance, grounding, complexity) independently, so a scenario can make only one judgement wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fakes.chat_model import ScriptedChatModel
from fakes.decider import FakeDecider
from fakes.reranker import FakeReranker
from fakes.retriever import InMemoryRetriever
from fakes.tools import RecordingToolRegistry
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from ragassist.platform.decisions.ports import ScoreAnswer
from support.settings import make_settings
from support.specs import need

TENANT_A = UUID("a0000000-0000-0000-0000-00000000000a")
TENANT_B = UUID("b0000000-0000-0000-0000-00000000000b")

ROUTE_QUESTION = "query_route"
SAFETY_QUESTION = "input_safety"
RELEVANCE_QUESTION = "chunk_relevance"
GROUNDING_QUESTION = "grounding_evaluation"

PLANNED_NODES = (
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
DOCS_PATH = [
    "guard_input",
    "router",
    "rewrite",
    "hybrid_retrieve",
    "rerank",
    "grade_relevance",
    "generate",
    "verify_grounding",
    "finalize",
]


class ScriptedDecider(FakeDecider):
    """Answers each named question from its own script (see the module docstring)."""

    def __init__(
        self,
        *,
        route: str = "rag_search",
        safe: bool = True,
        relevant: bool = True,
        grounded: bool = True,
        complexity: float = 2.0,
        grounding_prob: float = 0.9,
        relevance_prob: float = 0.9,
        safety_prob: float = 0.05,
    ) -> None:
        super().__init__("scripted")
        self.route = route
        self.safe = safe
        self.relevant = relevant
        self.grounded = grounded
        self.complexity = complexity
        self.grounding_prob = grounding_prob
        self.relevance_prob = relevance_prob
        self.safety_prob = safety_prob

    async def evaluate_choice(self, input_text, question):  # type: ignore[no-untyped-def]
        self.calls.append(("choice", question.name, input_text))
        from ragassist.platform.decisions.ports import ChoiceAnswer

        probs = {c: (0.95 if c == self.route else 0.0167) for c in question.choices}
        return ChoiceAnswer(question.name, self.route, 0.95, probs)

    async def evaluate_predicate(self, input_text, question):  # type: ignore[no-untyped-def]
        from ragassist.platform.decisions.ports import PredicateAnswer

        self.calls.append(("predicate", question.name, input_text))
        if question.name == SAFETY_QUESTION:
            return PredicateAnswer(
                question.name, self.safety_prob if self.safe else 0.97, not self.safe
            )
        if question.name == RELEVANCE_QUESTION:
            prob = self.relevance_prob if self.relevant else 0.1
            return PredicateAnswer(question.name, prob, prob >= 0.5)
        if question.name == GROUNDING_QUESTION:
            prob = self.grounding_prob if self.grounded else 0.2
            return PredicateAnswer(question.name, prob, self.grounded and prob >= 0.5)
        return PredicateAnswer(question.name, 0.9, True)

    async def evaluate_score(self, input_text, question):  # type: ignore[no-untyped-def]
        self.calls.append(("score", question.name, input_text))
        return ScoreAnswer(question.name, self.complexity, 0.9)


@dataclass
class Kit:
    decider: ScriptedDecider
    retriever: InMemoryRetriever
    reranker: FakeReranker
    tools: RecordingToolRegistry
    checkpointer: MemorySaver
    cheap: ScriptedChatModel
    strong: ScriptedChatModel
    settings: Any = field(default_factory=make_settings)

    def generator_tiers(self) -> dict[str, Any]:
        return {"cheap": self.cheap, "strong": self.strong}


@dataclass
class Turn:
    path: list[str]
    state: dict[str, Any]
    updates: list[dict[str, Any]]
    config: dict[str, Any]


def make_graph(kit: Kit, *, checkpointer: Any = None, **overrides: Any) -> Any:
    """Compile the planned graph with the kit's fakes."""
    build_graph = need("assistant.build_graph")
    kwargs: dict[str, Any] = {
        "settings": kit.settings,
        "decision_service": decision_service_for(kit.decider, kit.settings),
        "generator_tiers": kit.generator_tiers(),
        "retriever": kit.retriever,
        "reranker": kit.reranker,
        "tools": kit.tools,
        "checkpointer": checkpointer or kit.checkpointer,
    }
    kwargs.update(overrides)
    return build_graph(**kwargs)


def thread_config(tenant_id: UUID | str, conversation_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": f"{tenant_id}:{conversation_id}"}}


async def run_turn(
    graph: Any, *, question: str, principal: Any, conversation_id: str = "c1"
) -> Turn:
    config = thread_config(principal.tenant_id, conversation_id)
    payload = {"question": question, "principal": principal, "conversation_id": conversation_id}
    return await _drive(graph, payload, config)


async def resume_turn(
    graph: Any, *, decision: str, principal: Any, conversation_id: str = "c1"
) -> Turn:
    config = thread_config(principal.tenant_id, conversation_id)
    return await _drive(graph, Command(resume={"decision": decision}), config)


async def _drive(graph: Any, payload: Any, config: dict[str, Any]) -> Turn:
    updates: list[dict[str, Any]] = []
    async for update in graph.astream(payload, config, stream_mode="updates"):
        updates.append(update)
    state = (await graph.aget_state(config)).values
    path = [name for update in updates for name in update if not name.startswith("__")]
    return Turn(path=path, state=dict(state), updates=updates, config=config)


def paused(turn: Turn) -> bool:
    return any(name == "__interrupt__" for update in turn.updates for name in update)


class CountingSaver(MemorySaver):
    """A real in-memory checkpointer that records every read, for the tenant-guard scenarios."""

    def __init__(self) -> None:
        super().__init__()
        self.reads: list[Any] = []

    async def aget_tuple(self, config):  # type: ignore[no-untyped-def]
        self.reads.append(config)
        return await super().aget_tuple(config)


def make_kit(**decider_overrides: Any) -> Kit:
    """A fresh kit of fakes: a retriever with one tenant-A document, tools, two generator tiers."""
    retriever = InMemoryRetriever()
    retriever.add(
        chunk_id="a1",
        document_id="doc-a",
        tenant_id=TENANT_A,
        text="invoices are issued monthly on the first day",
        title="Billing guide",
        heading_path=("Invoices",),
        page=1,
    )
    retriever.add(
        chunk_id="g1",
        document_id="doc-g",
        tenant_id=None,
        text="world geography reference",
        title="Glossary",
    )
    tools = RecordingToolRegistry()
    tools.add("get_invoices", result={"total": 2400}, schema={"type": "object"})
    tools.add(
        "update_billing_email",
        write=True,
        result={"status": "success"},
        schema={"type": "object", "properties": {"new_email": {"type": "string"}}},
    )
    return Kit(
        decider=ScriptedDecider(**decider_overrides),
        retriever=retriever,
        reranker=FakeReranker("identity"),
        tools=tools,
        checkpointer=MemorySaver(),
        cheap=ScriptedChatModel(script=["Hello! How can I help?"], repeat_last=True),
        strong=ScriptedChatModel(script=["Invoices are issued monthly [1]."], repeat_last=True),
    )


def decision_service_for(decider: Any, settings: Any) -> Any:
    """The production DecisionService with one scripted decider in both chains."""
    from ragassist.platform.decisions.service import DecisionService
    from ragassist.shared.resilience import FallbackChain

    return DecisionService(
        settings=settings,
        router_chain=FallbackChain(name="router_chain", members=[decider]),
        decider_chain=FallbackChain(name="decider_chain", members=[decider]),
    )
