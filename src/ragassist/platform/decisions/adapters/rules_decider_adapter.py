"""Rule-based heuristic decider for ultra-low latency guards and classification."""

import re
from typing import Any
import unicodedata

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

# Common Cyrillic and Greek homoglyphs mapped to ASCII equivalents
_HOMOGLYPH_MAP = str.maketrans({
    "а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "х": "x", "у": "y",
    "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d",
    "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "І": "I", "Ј": "J",
    "К": "K", "М": "M", "О": "O", "Р": "P", "Т": "T", "Х": "X",
})
_ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200d\ufeff\u00ad]")


class RulesDeciderAdapter(Decider):
    """Deterministic, regex and pattern-matching decider for guardrails and routing."""

    def __init__(self) -> None:
        self._injection_patterns = [
            re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
            re.compile(r"dump\s+(?:the\s+)?system\s+prompt", re.IGNORECASE),
            re.compile(r"you\s+are\s+now\s+in\s+dan\s+mode", re.IGNORECASE),
            re.compile(r"system\s*prompt\s*override", re.IGNORECASE),
            re.compile(r"reveal\s+(?:your\s+)?(?:system\s+)?instructions", re.IGNORECASE),
            re.compile(r"jailbreak", re.IGNORECASE),
        ]

        self._saas_action_keywords = [
            "subscription",
            "invoice",
            "invoices",
            "billing",
            "subscription plan",
            "pricing plan",
            "billing plan",
            "my plan",
            "current plan",
            "seats",
            "seat",
            "account overview",
            "upgrade",
            "downgrade",
            "payment method",
        ]

        self._escalation_keywords = [
            "speak to a human",
            "real human",
            "transfer me",
            "human representative",
            "file a complaint",
            "get me a supervisor",
            "speak to agent",
            "talk to representative",
            "human support",
        ]

        self._general_chat_keywords = [
            "hello",
            "hi",
            "hey",
            "good morning",
            "good evening",
            "who are you",
            "thank you",
            "thanks",
            "bye",
            "goodbye",
        ]

        # Pre-compile word boundary patterns
        self._saas_action_patterns = [
            re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in self._saas_action_keywords
        ]
        self._escalation_patterns = [
            re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in self._escalation_keywords
        ]

    def _normalize_text(self, text: str) -> str:
        """Normalize Unicode, strip zero-width characters, and map homoglyphs."""
        norm = unicodedata.normalize("NFKC", text)
        cleaned = _ZERO_WIDTH_PATTERN.sub("", norm)
        return cleaned.translate(_HOMOGLYPH_MAP)

    @property
    def name(self) -> str:
        return "rules"

    async def evaluate_choice(
        self, input_text: str, question: ChoiceQuestion
    ) -> ChoiceAnswer:
        normalized = self._normalize_text(input_text)
        lower = normalized.lower().strip()

        # Check intent routing
        if set(question.choices) == {"rag_search", "saas_action", "general_chat", "human_escalation"}:
            if any(pat.search(lower) for pat in self._escalation_patterns):
                probs = {"human_escalation": 0.95, "rag_search": 0.02, "saas_action": 0.02, "general_chat": 0.01}
                return ChoiceAnswer(name=question.name, choice="human_escalation", confidence=0.95, probabilities=probs)

            if any(pat.search(lower) for pat in self._saas_action_patterns):
                probs = {"saas_action": 0.92, "rag_search": 0.05, "general_chat": 0.02, "human_escalation": 0.01}
                return ChoiceAnswer(name=question.name, choice="saas_action", confidence=0.92, probabilities=probs)

            if any(lower == k or lower.startswith(k + " ") for k in self._general_chat_keywords):
                probs = {"general_chat": 0.90, "rag_search": 0.05, "saas_action": 0.03, "human_escalation": 0.02}
                return ChoiceAnswer(name=question.name, choice="general_chat", confidence=0.90, probabilities=probs)

            # Default to rag_search
            probs = {"rag_search": 0.85, "general_chat": 0.05, "saas_action": 0.05, "human_escalation": 0.05}
            return ChoiceAnswer(name=question.name, choice="rag_search", confidence=0.85, probabilities=probs)

        # Generic choice fallback: pick first choice
        first_choice = question.choices[0] if question.choices else ""
        n = max(len(question.choices), 1)
        return ChoiceAnswer(
            name=question.name,
            choice=first_choice,
            confidence=1.0 / n,
            probabilities={c: 1.0 / n for c in question.choices},
        )

    async def evaluate_predicate(
        self, input_text: str, question: PredicateQuestion
    ) -> PredicateAnswer:
        normalized = self._normalize_text(input_text)
        instr_lower = question.instructions.lower()

        # Check prompt injection / safety
        if "prompt injection" in instr_lower or "jailbreak" in instr_lower or "toxic" in instr_lower:
            is_injected = any(pattern.search(normalized) for pattern in self._injection_patterns)
            prob = 0.95 if is_injected else 0.05
            return PredicateAnswer(
                name=question.name,
                probability=prob,
                verdict=is_injected,
            )

        # Generic predicate: default to True
        return PredicateAnswer(name=question.name, probability=0.5, verdict=True)

    async def evaluate_score(
        self, input_text: str, question: ScoreQuestion
    ) -> ScoreAnswer:
        levels = question.levels
        if not levels:
            return ScoreAnswer(name=question.name, score=0.5, confidence=0.5)

        mid_idx = len(levels) // 2
        score_val = float(levels[mid_idx].value)
        n = len(levels)
        probs = {str(lvl.value): 1.0 / n for lvl in levels}
        return ScoreAnswer(
            name=question.name,
            score=score_val,
            confidence=1.0 / n,
            probabilities=probs,
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
