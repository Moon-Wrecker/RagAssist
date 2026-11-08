"""Assistant graph state definitions and citation models."""

from __future__ import annotations

from typing import Any, TypedDict
from pydantic import BaseModel, Field

from ragassist.shared.security.jwt import Principal


class Citation(BaseModel):
    """Citation referencing a specific retrieved document chunk."""

    chunk_id: str
    document_id: str = ""
    title: str = ""
    page: int | None = None
    heading_path: list[str] | tuple[str, ...] = Field(default_factory=tuple)


class AnswerWithCitations(BaseModel):
    """Structured assistant answer with parsed chunk citations."""

    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)


class AssistantState(TypedDict, total=False):
    """Execution state for the LangGraph core assistant."""

    question: str
    principal: Principal
    conversation_id: str
    route: str
    complexity: float
    is_safe: bool
    current_query: str
    rewrite_count: int
    retrieve_count: int
    retrieved_chunks: list[Any]
    reranked_chunks: list[Any]
    graded_chunks: list[Any]
    answer: str
    citations: list[dict[str, Any]]
    is_grounded: bool
    grounding_score: float
    generate_count: int
    escalated: bool
    status: str
    model_used: str
    decider_used: str
    tool_calls: list[dict[str, Any]]
    error: str | None
