"""LLM-backed Structured Decider Adapter (Universal Fallback)."""

from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
import structlog

from ragassist.platform.decisions.ports import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    Decider,
    PredicateAnswer,
    PredicateQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)

logger = structlog.get_logger(__name__)


class StructuredChoice(BaseModel):
    choice: str = Field(description="Selected choice from the given options.")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0, description="Calibrated confidence rating between 0.0 and 1.0.")
    reasoning: str = Field(default="", description="Brief justification for the choice.")


class StructuredPredicate(BaseModel):
    verdict: bool = Field(description="True if the hypothesis statement holds, False otherwise.")
    probability: float = Field(default=0.5, ge=0.0, le=1.0, description="Calibrated probability that the statement is true.")
    reasoning: str = Field(default="", description="Brief justification.")


class StructuredScore(BaseModel):
    score: float = Field(default=0.5, ge=0.0, le=1.0, description="Normalized score rating between 0.0 and 1.0.")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0, description="Confidence in the score.")
    reasoning: str = Field(default="", description="Brief justification.")


class LLMStructuredDeciderAdapter(Decider):
    """Fallback Decider using LLM structured output schema enforcement."""

    def __init__(self, chat_model: BaseChatModel) -> None:
        self.chat_model = chat_model

    @property
    def name(self) -> str:
        return "llm_structured"

    async def evaluate_choice(
        self, input_text: str, question: ChoiceQuestion
    ) -> ChoiceAnswer:
        choices_str = ", ".join(f"'{c}'" for c in question.choices)
        prompt = (
            f"Input Text:\n{input_text}\n\n"
            f"Task: {question.instructions}\n"
            f"Allowed Choices: [{choices_str}]\n"
            f"Select exactly one choice and provide a calibrated confidence score between 0.0 and 1.0."
        )

        try:
            structured_llm = self.chat_model.with_structured_output(StructuredChoice)
            result: StructuredChoice = await structured_llm.ainvoke(
                [
                    SystemMessage(content="You are an accurate, calibrated classification decision engine."),
                    HumanMessage(content=prompt),
                ]
            )
            # Validate choice in options
            chosen = result.choice.strip()
            if chosen not in question.choices:
                # Find best fuzzy match or default to first
                for c in question.choices:
                    if c.lower() in chosen.lower():
                        chosen = c
                        break
                else:
                    chosen = question.choices[0] if question.choices else ""

            conf = max(min(result.confidence, 1.0), 0.0)
            if len(question.choices) > 1:
                rem = (1.0 - conf) / (len(question.choices) - 1)
                probs = {c: rem for c in question.choices}
                probs[chosen] = conf
            else:
                probs = {chosen: 1.0}

            return ChoiceAnswer(
                name=question.name,
                choice=chosen,
                confidence=result.confidence,
                probabilities=probs,
            )
        except Exception as exc:
            logger.warning("llm_structured.evaluate_choice_fallback", error=str(exc))
            first = question.choices[0] if question.choices else ""
            return ChoiceAnswer(
                name=question.name,
                choice=first,
                confidence=0.5,
                probabilities={c: 1.0 / max(len(question.choices), 1) for c in question.choices},
            )

    async def evaluate_predicate(
        self, input_text: str, question: PredicateQuestion
    ) -> PredicateAnswer:
        prompt = (
            f"Input Text:\n{input_text}\n\n"
            f"Hypothesis to evaluate: {question.instructions}\n"
            f"Return verdict=True if hypothesis holds, False otherwise, with calibrated probability [0.0, 1.0]."
        )

        try:
            structured_llm = self.chat_model.with_structured_output(StructuredPredicate)
            result: StructuredPredicate = await structured_llm.ainvoke(
                [
                    SystemMessage(content="You are a rigorous, calibrated verification engine."),
                    HumanMessage(content=prompt),
                ]
            )
            return PredicateAnswer(
                name=question.name,
                probability=result.probability,
                verdict=result.verdict,
            )
        except Exception as exc:
            logger.warning("llm_structured.evaluate_predicate_fallback", error=str(exc))
            return PredicateAnswer(
                name=question.name,
                probability=0.5,
                verdict=True,
            )

    async def evaluate_score(
        self, input_text: str, question: ScoreQuestion
    ) -> ScoreAnswer:
        levels_str = ", ".join(f"{lvl.value}: {lvl.label}" for lvl in question.levels)
        prompt = (
            f"Input Text:\n{input_text}\n\n"
            f"Evaluation criteria: {question.instructions}\n"
            f"Levels: [{levels_str}]\n"
            f"Rate on scale [0.0, 1.0] with confidence."
        )

        try:
            structured_llm = self.chat_model.with_structured_output(StructuredScore)
            result: StructuredScore = await structured_llm.ainvoke(
                [
                    SystemMessage(content="You are a calibrated grading evaluation engine."),
                    HumanMessage(content=prompt),
                ]
            )
            return ScoreAnswer(
                name=question.name,
                score=result.score,
                confidence=result.confidence,
                probabilities={},
            )
        except Exception as exc:
            logger.warning("llm_structured.evaluate_score_fallback", error=str(exc))
            return ScoreAnswer(
                name=question.name,
                score=0.5,
                confidence=0.5,
                probabilities={},
            )

    async def decide(self, input_text: str, questions: list[Question]) -> list[Answer]:
        results: list[Answer] = []
        for q in questions:
            if isinstance(q, ChoiceQuestion):
                results.append(await self.evaluate_choice(input_text, q))
            elif isinstance(q, PredicateQuestion):
                results.append(await self.evaluate_predicate(input_text, q))
            elif isinstance(q, ScoreQuestion):
                results.append(await self.evaluate_score(input_text, q))
        return results
