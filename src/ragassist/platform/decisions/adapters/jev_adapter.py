"""TypeSafe AI Jev Decider Adapter."""

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


class JevAdapter(Decider):
    """Adapter for TypeSafe AI Jev calibrated decision service."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str = "https://api.typesafe.ai/v1/decide",
        timeout_seconds: float = 1.0,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._api_key = api_key or self.settings.TYPESAFE_API_KEY
        self._endpoint = endpoint
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "jev"

    def _format_question(self, q: Question) -> dict[str, Any]:
        if isinstance(q, ChoiceQuestion):
            return {
                "type": "choice",
                "name": q.name,
                "prompt": q.instructions,
                "options": q.choices,
            }
        if isinstance(q, PredicateQuestion):
            return {
                "type": "predicate",
                "name": q.name,
                "prompt": q.instructions,
            }
        if isinstance(q, ScoreQuestion):
            return {
                "type": "score",
                "name": q.name,
                "prompt": q.instructions,
                "levels": [lvl.value for lvl in q.levels],
            }
        raise ValueError(f"Unsupported question type: {type(q)}")

    def _parse_answer(self, q: Question, raw: dict[str, Any]) -> Answer:
        if isinstance(q, ChoiceQuestion):
            choice = raw.get("choice", q.choices[0] if q.choices else "")
            confidence = float(raw.get("confidence", 0.0))
            probs = raw.get("probabilities", {c: 1.0 / max(len(q.choices), 1) for c in q.choices})
            return ChoiceAnswer(name=q.name, choice=choice, confidence=confidence, probabilities=probs)

        if isinstance(q, PredicateQuestion):
            prob = float(raw.get("probability", 0.0))
            verdict = bool(raw.get("verdict", False))
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
            "text": input_text,
            "queries": [self._format_question(q) for q in questions],
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results_list = data.get("results", [])
        answers_map = {res["name"]: res for res in results_list if "name" in res}
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
