"""Ports and domain contracts for the System One Decision Layer."""

from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias, runtime_checkable
from pydantic import BaseModel, Field

QuestionType = Literal["choice", "predicate", "score"]
RouteTarget = Literal["rag_search", "saas_action", "general_chat", "human_escalation"]


@dataclass(frozen=True)
class ChoiceQuestion:
    """Categorical choice question over discrete options."""

    name: str
    instructions: str
    choices: list[str]


@dataclass(frozen=True)
class PredicateQuestion:
    """Binary hypothesis evaluation question."""

    name: str
    instructions: str


@dataclass(frozen=True)
class ScoreLevel:
    """Discrete score level for ordinal rating."""

    value: int
    label: str


@dataclass(frozen=True)
class ScoreQuestion:
    """Ordinal score rating question across ordered levels."""

    name: str
    instructions: str
    levels: list[ScoreLevel]


Question: TypeAlias = ChoiceQuestion | PredicateQuestion | ScoreQuestion


@dataclass(frozen=True)
class ChoiceAnswer:
    """Answer to a ChoiceQuestion with calibrated probabilities."""

    name: str
    choice: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PredicateAnswer:
    """Answer to a PredicateQuestion with calibrated probability."""

    name: str
    probability: float
    verdict: bool


@dataclass(frozen=True)
class ScoreAnswer:
    """Answer to a ScoreQuestion with expected score and level probabilities."""

    name: str
    score: float
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RefusalAnswer:
    """Refusal answer when a question cannot be safely evaluated."""

    name: str
    reason: str


Answer: TypeAlias = ChoiceAnswer | PredicateAnswer | ScoreAnswer | RefusalAnswer


# --- High-level DTOs for RAG Pipeline Nodes ---


class RoutingDecision(BaseModel):
    """Categorical classification of user query intent."""

    route: RouteTarget
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    probabilities: dict[str, float] = Field(default_factory=dict)
    provider_used: str = ""


class SafetyVerdict(BaseModel):
    """Input guardrail verdict evaluating prompt injection, jailbreaks, and toxicity."""

    is_safe: bool
    violation_categories: list[str] = Field(default_factory=list)
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    provider_used: str = ""


class RelevanceScore(BaseModel):
    """Chunk relevance grading evaluating whether a retrieved chunk answers the query."""

    score: float = Field(ge=0.0, le=1.0)
    is_relevant: bool
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str = ""
    provider_used: str = ""


class GroundingVerdict(BaseModel):
    """Hallucination detection evaluating if response claims are grounded in context."""

    grounding_score: float = Field(ge=0.0, le=1.0)
    is_grounded: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str = ""
    provider_used: str = ""


@runtime_checkable
class Decider(Protocol):
    """Port for System-One decision models returning calibrated probabilities."""

    @property
    def name(self) -> str:
        """Adapter identifier."""
        ...

    async def decide(self, input_text: str, questions: list[Question]) -> list[Answer]:
        """Evaluate a batch of questions over input text in a single inference pass."""
        ...

    async def evaluate_choice(
        self, input_text: str, question: ChoiceQuestion
    ) -> ChoiceAnswer:
        """Evaluate a categorical choice question."""
        ...

    async def evaluate_predicate(
        self, input_text: str, question: PredicateQuestion
    ) -> PredicateAnswer:
        """Evaluate a binary predicate question."""
        ...

    async def evaluate_score(
        self, input_text: str, question: ScoreQuestion
    ) -> ScoreAnswer:
        """Evaluate an ordinal score rating question."""
        ...
