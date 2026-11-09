"""Scriptable fake ``Decider``: control the answer, its confidence, latency and failures."""

from __future__ import annotations

import asyncio
from typing import Any

from ragassist.platform.decisions.ports import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    PredicateAnswer,
    PredicateQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)


class FakeDecider:
    """Answers every question the same way unless told otherwise.

    * ``choice``       option to return (default: first option of the question)
    * ``confidence``   confidence of choice / score answers
    * ``probability``  probability of predicate answers (``verdict`` defaults to ``>= 0.5``)
    * ``delay``        seconds to wait before answering (to test timeouts)
    * ``error``        exception raised on every call
    * ``fail_times``   raise ``error`` only for the first N calls
    """

    def __init__(
        self,
        name: str = "fake",
        *,
        choice: str | None = None,
        confidence: float = 0.9,
        probability: float = 0.9,
        verdict: bool | None = None,
        score: float = 0.8,
        delay: float = 0.0,
        error: BaseException | None = None,
        fail_times: int | None = None,
    ) -> None:
        self._name = name
        self.choice = choice
        self.confidence = confidence
        self.probability = probability
        self.verdict = verdict
        self.score = score
        self.delay = delay
        self.error = error
        self.fail_times = fail_times
        self.calls: list[tuple[str, str, str]] = []  # (kind, question name, input text)

    @property
    def name(self) -> str:
        return self._name

    async def _enter(self, kind: str, question: Question, text: str) -> None:
        self.calls.append((kind, question.name, text))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            if self.fail_times is None:
                raise self.error
            if len([c for c in self.calls if c]) <= self.fail_times:
                raise self.error

    async def evaluate_choice(self, input_text: str, question: ChoiceQuestion) -> ChoiceAnswer:
        await self._enter("choice", question, input_text)
        chosen = self.choice if self.choice is not None else question.choices[0]
        others = [c for c in question.choices if c != chosen]
        rest = (1.0 - self.confidence) / len(others) if others else 0.0
        probabilities = {c: (self.confidence if c == chosen else rest) for c in question.choices}
        return ChoiceAnswer(question.name, chosen, self.confidence, probabilities)

    async def evaluate_predicate(
        self, input_text: str, question: PredicateQuestion
    ) -> PredicateAnswer:
        await self._enter("predicate", question, input_text)
        verdict = self.verdict if self.verdict is not None else self.probability >= 0.5
        return PredicateAnswer(question.name, self.probability, verdict)

    async def evaluate_score(self, input_text: str, question: ScoreQuestion) -> ScoreAnswer:
        await self._enter("score", question, input_text)
        return ScoreAnswer(question.name, self.score, self.confidence)

    async def decide(self, input_text: str, questions: list[Question]) -> list[Answer]:
        answers: list[Answer] = []
        for q in questions:
            if isinstance(q, ChoiceQuestion):
                answers.append(await self.evaluate_choice(input_text, q))
            elif isinstance(q, PredicateQuestion):
                answers.append(await self.evaluate_predicate(input_text, q))
            else:
                answers.append(await self.evaluate_score(input_text, q))
        return answers

    def __repr__(self) -> str:  # helpful in failure output
        return f"FakeDecider({self._name!r}, calls={len(self.calls)})"


def many(*deciders: Any) -> list[Any]:
    return list(deciders)
