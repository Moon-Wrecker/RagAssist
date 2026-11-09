"""Strands Local Decider Adapter."""

from typing import Any
import httpx
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
from ragassist.shared.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)


class StrandsDeciderAdapter(Decider):
    """Adapter for local Strands decision microservice."""

    def __init__(
        self,
        endpoint: str | None = None,
        timeout_seconds: float = 1.0,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._endpoint = endpoint or self.settings.STRANDS_DECIDER_ENDPOINT
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "strands_local"

    def _format_question(self, q: Question) -> dict[str, Any]:
        if isinstance(q, ChoiceQuestion):
            return {
                "type": "choice",
                "name": q.name,
                "instructions": q.instructions,
                "choices": q.choices,
            }
        if isinstance(q, PredicateQuestion):
            return {
                "type": "predicate",
                "name": q.name,
                "instructions": q.instructions,
            }
        if isinstance(q, ScoreQuestion):
            return {
                "type": "score",
                "name": q.name,
                "instructions": q.instructions,
                "levels": [lvl.value for lvl in q.levels],
            }
        raise ValueError(f"Unsupported question type: {type(q)}")

    def _parse_answer(self, q: Question, raw: dict[str, Any]) -> Answer:
        if isinstance(q, ChoiceQuestion):
            default_choice = q.choices[0] if q.choices else ""
            raw_choice = raw.get("choice", default_choice)
            if raw_choice not in q.choices:
                choice = default_choice
                confidence = 0.0
                probs = {c: 1.0 / max(len(q.choices), 1) for c in q.choices}
            else:
                choice = raw_choice
                confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
                raw_probs = raw.get("probabilities")
                if isinstance(raw_probs, dict) and set(raw_probs.keys()) == set(q.choices) and sum(raw_probs.values()) > 0:
                    total = sum(float(v) for v in raw_probs.values())
                    probs = {k: float(v) / total for k, v in raw_probs.items()}
                else:
                    probs = {c: 1.0 / max(len(q.choices), 1) for c in q.choices}
            return ChoiceAnswer(name=q.name, choice=choice, confidence=confidence, probabilities=probs)

        if isinstance(q, PredicateQuestion):
            prob = float(raw.get("probability", 0.0))
            verdict = bool(raw.get("verdict", prob >= 0.5))
            return PredicateAnswer(name=q.name, probability=prob, verdict=verdict)

        if isinstance(q, ScoreQuestion):
            score = float(raw.get("score", 0.0))
            confidence = float(raw.get("confidence", 0.0))
            probs = raw.get("probabilities", {})
            return ScoreAnswer(name=q.name, score=score, confidence=confidence, probabilities=probs)

        raise ValueError(f"Unknown question type: {type(q)}")

    async def decide(self, input_text: str, questions: list[Question]) -> list[Answer]:
        if not questions:
            return []

        payload = {
            "input": input_text,
            "questions": [self._format_question(q) for q in questions],
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()

        answers_map = {ans["name"]: ans for ans in data.get("answers", [])}
        return [self._parse_answer(q, answers_map.get(q.name, {})) for q in questions]

    async def evaluate_choice(
        self, input_text: str, question: ChoiceQuestion
    ) -> ChoiceAnswer:
        answers = await self.decide(input_text, [question])
        ans = answers[0]
        if isinstance(ans, ChoiceAnswer):
            return ans
        raise RuntimeError(f"Unexpected answer type: {type(ans)}")

    async def evaluate_predicate(
        self, input_text: str, question: PredicateQuestion
    ) -> PredicateAnswer:
        answers = await self.decide(input_text, [question])
        ans = answers[0]
        if isinstance(ans, PredicateAnswer):
            return ans
        raise RuntimeError(f"Unexpected answer type: {type(ans)}")

    async def evaluate_score(
        self, input_text: str, question: ScoreQuestion
    ) -> ScoreAnswer:
        answers = await self.decide(input_text, [question])
        ans = answers[0]
        if isinstance(ans, ScoreAnswer):
            return ans
        raise RuntimeError(f"Unexpected answer type: {type(ans)}")
